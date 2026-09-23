import urllib.error
import pytest
from cue import bootstrap
from cue.core import CueError

def test_outdated_helper_with_active_clients_requires_restart(monkeypatch,tmp_path):
    monkeypatch.setattr(bootstrap,'connection',lambda root:{'instance_id':'old'})
    def call(conn,path,body=None):
        if path=='/health':return {'helper_version':'old'}
        raise urllib.error.HTTPError('http://127.0.0.1/',400,'clients active',{},None)
    monkeypatch.setattr(bootstrap,'call',call)
    monkeypatch.setattr(bootstrap.subprocess,'Popen',lambda *a,**k:pytest.fail('must not start a competing helper'))
    with pytest.raises(CueError,match='close other Cue windows') as exc:
        bootstrap.ensure(tmp_path/'runtime')
    assert exc.value.code=='HELPER_RESTART_REQUIRED'

def test_outdated_idle_helper_is_replaced(monkeypatch,tmp_path):
    state={'version':'old'}
    monkeypatch.setattr(bootstrap,'connection',lambda root:{'instance_id':state['version']})
    def call(conn,path,body=None):
        if path=='/shutdown':state['version']='stopped';return {'ok':True}
        if state['version']=='stopped':raise OSError('old helper stopped')
        return {'helper_version':state['version']}
    monkeypatch.setattr(bootstrap,'call',call)
    class Process:
        def poll(self):return None
    def spawn(*args,**kwargs):
        state['version']=bootstrap.HELPER_VERSION
        return Process()
    monkeypatch.setattr(bootstrap.subprocess,'Popen',spawn)
    assert bootstrap.ensure(tmp_path/'runtime')['instance_id']==bootstrap.HELPER_VERSION
