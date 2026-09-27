import json
import queue
import threading
import time
import urllib.error
import urllib.request
import pytest
from cue.core import Cue, CueError, Settings
from cue.media import Media
from cue.service import Server, Session, Supervisor

@pytest.fixture
def sup(tmp_path):
    s=Supervisor(tmp_path/'runtime',tmp_path/'models',clock=lambda:100)
    s.clients['a']=100;s.clients['b']=100
    media=Media('/missing', 'signature', 1, 'stream', 100000, 0, 1, 1)
    session=Session('1'*32,'a',media,Settings(),'source','translated',0,last_seen=100)
    s.sessions[session.id]=session
    return s

def test_prepared_is_not_installed_and_ack_is_fenced(sup):
    s=next(iter(sup.sessions.values()))
    sup.cache.put(s.profile,0,10000,[Cue('a',0,500,'hi')],{'code':'en'})
    sup.publish(s)
    assert s.prepared==[[0,10000]] and s.installed==[]
    assert not sup.snapshot(s)['ready']
    base=f'/v1/sessions/{s.id}'
    ack={'revision':s.revision,'sha256':s.artifact['sha256'],'seek_epoch':0,'success':True}
    sup.request('POST',base+'/render-ack',ack,'a')
    assert sup.snapshot(s)['ready']
    sup.request('PUT',base+'/playback',{'client_seq':1,'seek_epoch':1,'position_ms':60000,'rate':1},'a')
    assert s.installed==[]
    with pytest.raises(CueError):sup.request('POST',base+'/render-ack',ack,'a')

def test_cross_client_and_out_of_order_updates(sup):
    s=next(iter(sup.sessions.values()));base=f'/v1/sessions/{s.id}'
    with pytest.raises(CueError,match='NOT_FOUND'):sup.request('GET',base+'/snapshot',{},'b')
    body={'client_seq':2,'seek_epoch':0,'position_ms':2000,'rate':1}
    sup.request('PUT',base+'/playback',body,'a')
    with pytest.raises(CueError,match='STALE_SEQUENCE'):sup.request('PUT',base+'/playback',body,'a')
    assert s.position==2000

@pytest.mark.parametrize('rate',[0,-1,float('nan'),float('inf'),100])
def test_invalid_rate_does_not_mutate(sup,rate):
    s=next(iter(sup.sessions.values()))
    with pytest.raises(CueError):sup.request('PUT',f'/v1/sessions/{s.id}/playback',{'client_seq':1,'seek_epoch':5,'position_ms':2000,'rate':rate},'a')
    assert s.seq==0 and s.epoch==0

def test_delete_client_preserves_other_sessions(sup):
    s=next(iter(sup.sessions.values()))
    sup.sessions['2'*32]=Session('2'*32,'b',s.media,Settings(),'s','p',0,last_seen=100)
    sup.remove_client('a')
    assert list(sup.sessions)==['2'*32]

def test_remux_is_background_and_only_one_copy_runs(sup,monkeypatch,tmp_path):
    source=tmp_path/'input.mkv';source.write_bytes(b'fixture')
    output=tmp_path/'new.mkv'
    release=threading.Event()
    copying=threading.Event()
    def copy(src,dest,progress,cancel=None):
        assert src==str(source) and dest==str(output)
        progress('copying',35);copying.set()
        assert release.wait(2)
        return dest
    monkeypatch.setattr('cue.service.remux',copy)
    started=sup.request('POST','/v1/remux',{'source':str(source),'output':str(output)},'a')
    assert started['state']=='running'
    assert copying.wait(2)
    current=sup.request('GET',f"/v1/remux/{started['job_id']}",{},'a')
    assert current['state']=='running' and current['phase']=='copying' and current['progress_pct']==35
    with pytest.raises(CueError,match='REMUX_ACTIVE'):
        sup.request('POST','/v1/remux',{'source':str(source),'output':str(output)},'a')
    release.set()
    for _ in range(50):
        result=sup.request('GET',f"/v1/remux/{started['job_id']}",{},'a')
        if result['state']=='complete':break
        time.sleep(.01)
    assert result['state']=='complete' and result['path']==str(output)
    assert result['phase']=='complete' and result['progress_pct']==100

def test_no_shutdown_with_active_clients(sup):
    with pytest.raises(CueError,match='CLIENTS_ACTIVE'):sup.request('POST','/v1/shutdown',{},None)

def test_stale_result_cached_but_not_published(sup):
    s=next(iter(sup.sessions.values()));s.epoch=1
    class MediaOK:
        def unchanged(self):return True
    sup.busy={'session':s.id,'job_id':'job','epoch':0,'media_obj':MediaOK(),'source_profile':'source','profile':'translated','range':[0,10000]}
    sup.outbox=queue.Queue()
    sup.outbox.put({'job_id':'job','result':{'source':[],'rendered':[],'language':{'code':'und'},'timings':{}}})
    sup.tick()
    assert sup.cache.read('translated')[0]==[[0,10000]]
    assert s.artifact is None and s.installed==[]

def test_loopback_auth_origin_and_host(sup):
    server=Server(sup);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/v1/health'
    try:
        for headers in [{},{'Authorization':'Bearer wrong'},{'Authorization':'Bearer '+sup.token,'Origin':'https://evil.example'},{'Authorization':'Bearer '+sup.token,'Host':'evil.example'}]:
            with pytest.raises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(url,headers=headers))
            assert e.value.code==403
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+sup.token})) as r:
            assert json.load(r)['instance_id']==sup.instance
    finally:server.shutdown();server.server_close()

def test_new_target_inside_source_chunk_reuses_whole_aligned_chunk(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));s.position=4000;sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.cache.put('source',0,9000,[Cue('known',0,8000,'already aligned')],{'code':'en'})
    sup.tick()
    job=sup.inbox.get_nowait()
    assert job['range']==[0,9000]
    assert job['cached_source']['cues'][0]['id']=='known'

def test_source_boundary_error_is_session_error_not_supervisor_crash(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.cache.put('source',0,10000,[Cue('one',0,8000,'first')],{'code':'en'})
    sup.cache.put('source',4000,14000,[Cue('two',4000,13000,'conflict')],{'code':'en'})
    sup.tick()
    assert s.error['code']=='ALIGNMENT_FAILED' and sup.inbox.empty()

def test_alignment_failure_retries_once_with_shorter_window_and_more_context(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.busy={'session':s.id,'job_id':'first','epoch':0,'media_obj':s.media,'source_profile':'source','profile':'translated','range':[0,16000],'attempt':0}
    sup.outbox.put({'job_id':'first','error':{'code':'ALIGNMENT_FAILED'}})
    sup.tick();retry=sup.inbox.get_nowait()
    assert retry['range']==[0,8000] and retry['attempt']==1
    assert retry['settings']['context_ms']==2000
    sup.outbox.put({'job_id':retry['job_id'],'error':{'code':'ALIGNMENT_FAILED','detail':'collapsed alignment span'}})
    sup.tick();following=sup.inbox.get_nowait()
    # The half that failed twice is a hole; the session keeps going after it.
    assert s.error is None and s.state=='preparing'
    assert s.failed==[[0,8000]] and s.prepared==[]
    assert following['range'][0]==8000
    assert sup.snapshot(s)['failure']=={'code':'ALIGNMENT_FAILED','detail':'collapsed alignment span','range':[0,8000]}

def test_uncertain_language_retries_with_longer_audio_then_keeps_coverage_hole(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.busy={'session':s.id,'job_id':'first','epoch':0,'profile':s.profile,'media_obj':s.media,
              'source_profile':s.source_profile,'range':[0,10000],'attempt':0,'started':100}
    sup.outbox.put({'job_id':'first','error':{'code':'LANGUAGE_UNCERTAIN'}})
    sup.tick();retry=sup.inbox.get_nowait()
    assert retry['range']==[0,20000] and retry['attempt']==1
    sup.outbox.put({'job_id':retry['job_id'],'error':{'code':'LANGUAGE_UNCERTAIN'}})
    sup.tick();following=sup.inbox.get_nowait()
    assert s.skipped_language==[[0,20000]] and s.prepared==[]
    assert following['range'][0]==20000
    assert s.error is None

def test_progress_reports_detected_language_only_for_current_epoch(sup):
    s=next(iter(sup.sessions.values()))
    sup.worker=type('LiveWorker',(),{'is_alive':lambda self:True})()
    sup.busy={'session':s.id,'job_id':'job','epoch':0,'profile':s.profile,'started':100}
    sup.outbox=queue.Queue()
    sup.outbox.put({'job_id':'job','stage':'aligning','language':{'code':'el','status':'tentative'}})
    sup.tick()
    snapshot=sup.snapshot(s)
    assert snapshot['stage']=='aligning' and snapshot['language']['code']=='el'
    s.epoch=1
    sup.outbox.put({'job_id':'job','stage':'translating','language':{'code':'en'}})
    sup.tick()
    assert s.language['code']=='el' and sup.snapshot(s)['stage']=='idle'

def test_remux_cancel_marks_job_cancelled_and_allows_a_new_copy(sup,monkeypatch,tmp_path):
    source=tmp_path/'input.mkv';source.write_bytes(b'fixture')
    output=tmp_path/'new.mkv'
    copying=threading.Event()
    def copy(src,dest,progress,cancel):
        progress('copying',10);copying.set()
        assert cancel.wait(2)
        raise CueError('REMUX_CANCELLED')
    monkeypatch.setattr('cue.service.remux',copy)
    started=sup.request('POST','/v1/remux',{'source':str(source),'output':str(output)},'a')
    assert copying.wait(2)
    requested=sup.request('POST',f"/v1/remux/{started['job_id']}/cancel",{},'a')
    assert requested['cancel_requested'] is True
    for _ in range(100):
        result=sup.request('GET',f"/v1/remux/{started['job_id']}",{},'a')
        if result['state']!='running':break
        time.sleep(.01)
    assert result['state']=='cancelled' and 'error' not in result
    assert not sup.remux_running()
    again=sup.request('POST',f"/v1/remux/{started['job_id']}/cancel",{},'a')
    assert again['cancel_requested'] is False
    with pytest.raises(CueError,match='NOT_FOUND'):sup.request('POST','/v1/remux/missing/cancel',{},'a')


def failing_job(sup,s,monkeypatch,code,attempt=0,window=(0,16000)):
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.busy={'session':s.id,'job_id':'job','epoch':0,'media_obj':s.media,'source_profile':s.source_profile,
              'profile':s.profile,'range':list(window),'attempt':attempt,'started':100}
    sup.outbox.put({'job_id':'job','error':{'code':code}})
    sup.tick()

def test_translation_failure_becomes_a_hole_without_a_second_attempt(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    failing_job(sup,s,monkeypatch,'TRANSLATION_FAILED')
    following=sup.inbox.get_nowait()
    assert s.failed==[[0,16000]] and s.error is None and following['range'][0]==16000

def test_a_failure_of_cue_itself_still_stops_the_session(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    failing_job(sup,s,monkeypatch,'MODEL_LOAD_FAILED')
    assert s.error=={'code':'MODEL_LOAD_FAILED'} and s.state=='error' and sup.inbox.empty() and s.failed==[]

def test_retry_prepares_failed_and_skipped_holes_again(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    failing_job(sup,s,monkeypatch,'TRANSLATION_FAILED')
    sup.inbox.get_nowait();sup.busy=None
    s.skipped_language=[[40000,60000]]
    sup.request('POST',f'/v1/sessions/{s.id}/actions',{'action':'retry'},'a')
    assert s.failed==[] and s.skipped_language==[] and s.last_failure is None
    sup.tick()
    assert sup.inbox.get_nowait()['range'][0]==0

def test_ready_looks_past_holes_but_the_caption_buffer_does_not(sup):
    s=next(iter(sup.sessions.values()))
    s.installed=[[0,10000]];s.failed=[[10000,26000]];s.position=9000
    snap=sup.snapshot(s)
    assert snap['ready'] is True
    assert snap['buffer_media_ms']==1000
    s.failed=[]
    assert sup.snapshot(s)['ready'] is False

def test_first_window_at_the_playhead_keeps_the_startup_floor_and_later_windows_the_minimum(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.tick()
    first=sup.inbox.get_nowait()
    assert first['range']==[0,10000] and first['min_commit_ms']==8000
    sup.busy=None
    sup.cache.put(s.source_profile,0,10000,[Cue('a',0,500,'hi')],{'code':'en'})
    sup.cache.put(s.profile,0,10000,[Cue('a',0,500,'hi')],{'code':'en'})
    sup.tick()
    second=sup.inbox.get_nowait()
    assert second['range']==[10000,26000] and second['min_commit_ms']==2000

def test_session_creation_reads_user_glossary_files_and_keys_the_translation_profile_on_them(sup,monkeypatch,tmp_path):
    video=tmp_path/'film.mp4';video.touch()
    media=Media(str(video),'sig',1,'stream',100000,0,1,1)
    monkeypatch.setattr(Media,'open',classmethod(lambda cls,path,hint:media))
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    # The speech model key reads the model manifest; the test is about glossary files, not models.
    monkeypatch.setattr(sup,'speech_model_key',lambda:'gemma-e2b@test')
    def create(request_id):
        snap=sup.request('POST','/v1/sessions',{'request_id':request_id,'path':str(video),'settings':{'target':'zh-TW'}},'a')
        return sup.sessions[snap['session_id']]
    plain=create('one')
    (tmp_path/'film.cue-glossary.json').write_text(json.dumps({'zh-TW':{'Nash':'納許'}}),encoding='utf-8')
    pinned=create('two')
    assert plain.user_glossary=={} and pinned.user_glossary=={'Nash':'納許'}
    assert plain.source_profile==pinned.source_profile and plain.profile!=pinned.profile

def test_jobs_carry_previous_lines_and_the_glossary_and_learned_names_are_stored(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));s.position=20000;sup.active=s.id;s.user_glossary={'Nash':'納許'}
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    for i in range(14):
        sup.cache.put(s.source_profile,i*1000,(i+1)*1000,[Cue(f's{i}',i*1000,i*1000+500,f'line {i}')],{'code':'en'})
    for i in range(8):
        sup.cache.put(s.profile,i*1000,(i+1)*1000,[Cue(f'r{i}',i*1000,i*1000+500,f'譯{i}')],{'code':'en'})
    sup.cache.add_names(s.media.signature,'zh-TW',{'Hansen':'漢森'},0)
    sup.tick()
    job=sup.inbox.get_nowait()
    assert job['range'][0]==20000
    assert [c['id'] for c in job['previous_source']]==[f's{i}' for i in range(2,14)]
    assert [c['id'] for c in job['previous_rendered']]==[f'r{i}' for i in range(2,8)]
    assert job['glossary']['user']=={'Nash':'納許'} and job['glossary']['learned']==[['Hansen','漢森',0]]
    sup.outbox.put({'job_id':job['job_id'],'result':{'source':[],'rendered':[],'language':{'code':'en'},'timings':{},
                    'committed_range':[20000,30000],'names':{'Nash':'納什','Parcher':'帕徹'}}})
    sup.busy['job_id']=job['job_id']
    sup.outbox.queue[-1]['result']['source']=[{'id':'x','start_ms':20000,'end_ms':20400,'text':'Parcher, Parcher.'}]
    sup.tick()
    # Sol would be pinned by the built-in table; Parcher is not in it and is mentioned twice.
    assert sup.cache.names(s.media.signature,'zh-TW')==[['Parcher','帕徹',20000],['Hansen','漢森',0]]

def test_learned_names_skip_builtin_keys_and_words_the_film_uses_in_lowercase(sup,monkeypatch):
    s=next(iter(sup.sessions.values()));s.position=20000;sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.cache.put(s.source_profile,0,10000,[Cue('s0',0,500,'I mean it seriously, Nash. Nash?')],{'code':'en'})
    sup.tick()
    job=sup.inbox.get_nowait()
    assert job['glossary']['builtin']['John']=='約翰'
    sup.outbox.put({'job_id':job['job_id'],'result':{'source':[],'rendered':[],'language':{'code':'en'},'timings':{},
                    'committed_range':[20000,30000],'names':{'Seriously':'認真','John':'約翰','Nash':'納許'}}})
    sup.tick()
    assert sup.cache.names(s.media.signature,'zh-TW')==[['Nash','納許',20000]]

def test_names_the_supervisor_skips_are_logged_with_the_reason(sup,monkeypatch,capsys):
    s=next(iter(sup.sessions.values()));s.position=20000;sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.cache.put(s.source_profile,0,10000,[Cue('s0',0,500,'I mean it seriously, Bender. Bender and Nash. Nash?')],{'code':'en'})
    sup.cache.add_names(s.media.signature,'zh-TW',{'Baker':'貝克'},0)
    sup.tick();job=sup.inbox.get_nowait()
    sup.outbox.put({'job_id':job['job_id'],'result':{'source':[],'rendered':[],'language':{'code':'en'},'timings':{},
                    'committed_range':[20000,30000],'names':{'Seriously':'認真','John':'約翰','Bender':'貝克','Nash':'納許'}}})
    capsys.readouterr()
    sup.tick()
    events=[json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]
    skipped=[e for e in events if e.get('event')=='names_skipped']
    assert skipped==[{'event':'names_skipped','pinned':['John'],'common':['Seriously'],'owned':['Bender'],'once':[]}]

def test_a_name_is_stored_only_once_the_film_has_mentioned_it_twice(sup,monkeypatch,capsys):
    s=next(iter(sup.sessions.values()));s.position=20000;sup.active=s.id
    monkeypatch.setattr(Media,'unchanged',lambda self:True)
    sup.inbox=queue.Queue();sup.outbox=queue.Queue();monkeypatch.setattr(sup,'start_worker',lambda:None)
    sup.cache.put(s.source_profile,0,10000,[Cue('s0',0,500,'Come on, Bender. Enjoy your Punch.')],{'code':'en'})
    sup.tick();job=sup.inbox.get_nowait()
    sup.outbox.put({'job_id':job['job_id'],'result':{'source':[{'id':'s1','start_ms':20000,'end_ms':20500,'text':'Bender is here.'}],'rendered':[],
                    'language':{'code':'en'},'timings':{},'committed_range':[20000,30000],'names':{'Bender':'本德','Punch':'潘奇'}}})
    capsys.readouterr();sup.tick()
    assert sup.cache.names(s.media.signature,'zh-TW')==[['Bender','本德',20000]]
    events=[json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith('{')]
    assert [e for e in events if e.get('event')=='names_skipped']==[{'event':'names_skipped','pinned':[],'common':[],'owned':[],'once':['Punch']}]
