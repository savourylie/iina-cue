import sqlite3
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

def test_a_stretch_without_speech_keeps_the_detected_language(tmp_path):
    cache=Cache(tmp_path/'cache');cache.register('p','media','original')
    english={'code':'en','status':'tentative'};unknown={'code':'und','status':'unknown','method':'voice_activity'}
    cache.put('p',0,10000,[Cue('a',500,900,'hello')],english)
    cache.put('p',10000,26000,[],unknown)
    assert cache.read('p')[2]==english
    cache.put('p',26000,42000,[Cue('b',27000,28000,'bonjour')],{'code':'fr','status':'tentative'})
    assert cache.read('p')[2]['code']=='fr'

def test_only_stretches_without_speech_report_an_unknown_language(tmp_path):
    cache=Cache(tmp_path/'cache');cache.register('p','media','original')
    cache.put('p',0,16000,[],{'code':'und','status':'unknown','method':'voice_activity'})
    assert cache.read('p')[2]['code']=='und'

def test_learned_names_keep_the_first_rendering_and_clear_with_the_film(tmp_path):
    cache=Cache(tmp_path/'cache');cache.register('p','media','zh-TW')
    assert cache.add_names('media','zh-TW',{'Nash':'納許','Hansen':'漢森'},120000)==2
    assert cache.add_names('media','zh-TW',{'Nash':'納什','Sol':'索爾'},136000)==1
    assert cache.names('media','zh-TW')==[['Sol','索爾',136000],['Hansen','漢森',120000],['Nash','納許',120000]]
    assert cache.names('media','ja')==[]
    assert cache.add_names('media','zh-TW',{},0)==0
    cache.clear_media('media')
    assert cache.names('media','zh-TW')==[]

def test_a_version_one_cache_gains_the_glossary_table(tmp_path):
    root=tmp_path/'cache';root.mkdir()
    db=sqlite3.connect(root/'cache.sqlite3')
    db.executescript("""CREATE TABLE chunks (profile TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
        payload TEXT NOT NULL, updated REAL NOT NULL DEFAULT (unixepoch()), PRIMARY KEY(profile, start, end));
      CREATE TABLE profiles (profile TEXT PRIMARY KEY, media TEXT NOT NULL, target TEXT NOT NULL);
      PRAGMA user_version=1;""")
    db.close()
    cache=Cache(root)
    assert cache.db.execute('PRAGMA user_version').fetchone()[0]==2
    assert cache.add_names('m','zh-TW',{'Nash':'納許'},0)==1
