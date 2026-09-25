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
