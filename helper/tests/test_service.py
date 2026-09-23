import json
import queue
import threading
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
    sup.outbox.put({'job_id':retry['job_id'],'error':{'code':'ALIGNMENT_FAILED'}})
    sup.tick()
    assert s.error['code']=='ALIGNMENT_FAILED' and sup.inbox.empty()
