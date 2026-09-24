import json
import os
import subprocess
import urllib.error
from pathlib import Path
import pytest
from cue import bootstrap
from cue.core import CueError, digest

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

def test_development_paths_stay_in_the_checkout(monkeypatch,tmp_path):
    monkeypatch.delenv('CUE_INSTALLED',raising=False)
    monkeypatch.delenv('CUE_HOME',raising=False)
    monkeypatch.delenv('CUE_MODELS',raising=False)
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    assert bootstrap.runtime_root()==(bootstrap.PROJECT/'.runtime').resolve()
    assert bootstrap.models_root()==(bootstrap.PROJECT/'.runtime'/'models').resolve()

def test_installed_mode_defaults_to_application_support(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    monkeypatch.delenv('CUE_HOME',raising=False)
    monkeypatch.delenv('CUE_MODELS',raising=False)
    assert bootstrap.support_dir()==tmp_path.resolve()
    assert bootstrap.runtime_root()==tmp_path.resolve()
    assert bootstrap.models_root()==(tmp_path/'models').resolve()
    assert bootstrap.bundled_bin_dir()==(tmp_path/'runtime'/'bin').resolve()

def test_support_dir_uses_the_user_application_support_directory(monkeypatch):
    monkeypatch.delenv('CUE_SUPPORT',raising=False)
    assert bootstrap.support_dir()==(Path.home()/'Library'/'Application Support'/'Cue').resolve()

def test_install_marker_selects_installed_paths(monkeypatch,tmp_path):
    monkeypatch.delenv('CUE_INSTALLED',raising=False)
    monkeypatch.delenv('CUE_HOME',raising=False)
    monkeypatch.delenv('CUE_MODELS',raising=False)
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    (tmp_path/'installed').write_text('1\n')
    assert bootstrap.runtime_root()==tmp_path.resolve()
    assert bootstrap.models_root()==(tmp_path/'models').resolve()

def test_development_opt_out_ignores_the_install_marker(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','0')
    monkeypatch.delenv('CUE_HOME',raising=False)
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    (tmp_path/'installed').write_text('1\n')
    assert bootstrap.runtime_root()==(bootstrap.PROJECT/'.runtime').resolve()

def test_explicit_data_paths_override_installed_defaults(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path/'support'))
    monkeypatch.setenv('CUE_HOME',str(tmp_path/'data'))
    monkeypatch.setenv('CUE_MODELS',str(tmp_path/'models'))
    assert bootstrap.runtime_root()==(tmp_path/'data').resolve()
    assert bootstrap.models_root()==(tmp_path/'models').resolve()

def test_installed_mode_restores_home_when_the_environment_has_none(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    monkeypatch.delenv('HOME',raising=False)
    assert bootstrap.installed_mode() is True
    assert os.environ['HOME']==str(Path.home())

def test_symlink_install_marker_is_rejected(monkeypatch,tmp_path):
    monkeypatch.delenv('CUE_INSTALLED',raising=False)
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    (tmp_path/'real').write_text('1\n')
    (tmp_path/'installed').symlink_to(tmp_path/'real')
    with pytest.raises(CueError,match='UNSAFE_PATH'):bootstrap.runtime_root()

def test_development_manifest_stays_in_the_checkout(monkeypatch):
    monkeypatch.setenv('CUE_INSTALLED','0')
    assert bootstrap.model_manifest_path()==(bootstrap.PROJECT/'models'/'manifest.json').resolve()

def test_installed_manifest_comes_from_the_runtime(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    manifest=tmp_path/'runtime'/'manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"schema_version":1,"assets":[]}\n')
    assert bootstrap.model_manifest_path()==manifest.resolve()

def test_installed_mode_rejects_a_missing_or_symlinked_manifest(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    with pytest.raises(CueError,match='model manifest') as missing:
        bootstrap.model_manifest_path()
    assert missing.value.code=='SETUP_REQUIRED'
    runtime=tmp_path/'runtime'
    runtime.mkdir()
    real=tmp_path/'real-manifest.json'
    real.write_text('{}\n')
    (runtime/'manifest.json').symlink_to(real)
    with pytest.raises(CueError,match='model manifest'):bootstrap.model_manifest_path()

def test_symlink_runtime_directory_is_rejected(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    (tmp_path/'real-runtime').mkdir()
    (tmp_path/'runtime').symlink_to(tmp_path/'real-runtime')
    with pytest.raises(CueError,match='UNSAFE_PATH'):bootstrap.bundled_bin_dir()

def test_installed_ensure_stops_before_starting_when_the_manifest_is_missing(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    monkeypatch.setattr(bootstrap.subprocess,'Popen',lambda *a,**k:pytest.fail('must not start a helper'))
    with pytest.raises(CueError,match='model manifest') as exc:
        bootstrap.ensure(tmp_path)
    assert exc.value.code=='SETUP_REQUIRED'

def test_supervisor_hashes_the_runtime_manifest_in_installed_mode(monkeypatch,tmp_path):
    monkeypatch.setenv('CUE_INSTALLED','1')
    monkeypatch.setenv('CUE_SUPPORT',str(tmp_path))
    manifest=tmp_path/'runtime'/'manifest.json'
    manifest.parent.mkdir(parents=True)
    payload={"schema_version":1,"assets":[{"name":"installed-only"}]}
    manifest.write_text(json.dumps(payload))
    from cue.service import Supervisor
    supervisor=Supervisor(tmp_path,tmp_path/'models',clock=lambda:100)
    checkout=json.loads((bootstrap.PROJECT/'models'/'manifest.json').read_text())
    assert supervisor.manifest_hash==digest(payload)
    assert supervisor.manifest_hash!=digest(checkout)

def test_runtime_build_ships_a_scanned_launcher_and_manifest():
    script=(bootstrap.PROJECT/'scripts'/'build-runtime').read_text()
    launcher=script.index('scripts/runtime-cue-helper')
    manifest=script.index('models/manifest.json')
    scan=script.index('scan "$STAGE"')
    assert launcher<scan and manifest<scan
    launcher_text=(bootstrap.PROJECT/'scripts'/'runtime-cue-helper').read_text()
    assert 'CUE_INSTALLED=1' in launcher_text
    assert '/opt/homebrew' not in launcher_text
    subprocess.run(['/bin/sh','-n',str(bootstrap.PROJECT/'scripts'/'runtime-cue-helper')],check=True)
