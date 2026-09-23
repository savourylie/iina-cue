import pytest
from cue.core import Cue, CueError
from cue.storage import Cache, atomic_write

def test_partial_export_and_no_overwrite(tmp_path):
    cache=Cache(tmp_path/'cache')
    cache.put('p',60000,61000,[Cue('id',60000,60500,'text')],{'code':'en'})
    dest=cache.export('p',100000,tmp_path/'test.srt',{})
    assert dest.name=='test.partial.srt'
    assert '"complete_movie": false' in dest.with_suffix('.json').read_text()
    with pytest.raises(CueError): cache.export('p',100000,tmp_path/'test.srt',{})

def test_export_sidecar_collision_leaves_no_orphan_srt(tmp_path):
    cache=Cache(tmp_path/'cache')
    cache.put('p',0,1000,[Cue('id',0,500,'text')],{'code':'en'})
    sidecar=tmp_path/'test.json';sidecar.write_text('keep me')
    with pytest.raises(CueError,match='OUTPUT_EXISTS'):
        cache.export('p',1000,tmp_path/'test.srt',{})
    assert not (tmp_path/'test.srt').exists()
    assert sidecar.read_text()=='keep me'

def test_profiles_isolated_and_cache_survives_reopen(tmp_path):
    cache=Cache(tmp_path/'cache');cache.register('en','media','en');cache.register('zh','media','zh-TW')
    cache.put('en',0,1000,[Cue('a',0,500,'hello')],{'code':'en'})
    cache.put('zh',0,1000,[Cue('a',0,500,'你好')],{'code':'en'})
    assert Cache(tmp_path/'cache').read('en')[1][0].text=='hello'
    assert cache.read('zh')[1][0].text=='你好'
    cache.clear_media('media');assert cache.status()['chunks']==0

def test_atomic_no_symlink(tmp_path):
    dest=tmp_path/'dest';dest.symlink_to(tmp_path/'other')
    with pytest.raises(CueError): atomic_write(dest,'x')

def test_failed_chunk_not_committed(tmp_path):
    cache=Cache(tmp_path/'cache')
    with pytest.raises(CueError):cache.put('p',0,1000,[Cue('a',1,0,'x')],{})
    assert cache.read('p')[0]==[]
