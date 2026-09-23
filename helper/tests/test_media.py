import subprocess
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from cue.core import CueError
from cue.media import Media, binary, extract, local_media, select_stream

@pytest.fixture(scope='session')
def fixture(tmp_path_factory):
    root=tmp_path_factory.mktemp('media')
    path=root/'多音軌 $test; "quote".mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=64x64:r=10:d=4','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=4','-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=4','-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-c:a','pcm_s16le','-metadata:s:a:0','language=eng','-metadata:s:a:1','language=jpn','-y',str(path)],check=True)
    return path

def test_track_mapping_uses_ff_index_not_mpv_id(fixture,tmp_path):
    media=Media.open(str(fixture),{'mpv_id':1,'ff_index':2,'language':'jpn'})
    assert media.stream_index==2
    dest=tmp_path/'out.wav'; mapping=extract(media,1000,2000,dest)
    data,sr=sf.read(dest)
    peak=np.argmax(abs(np.fft.rfft(data)))*sr/len(data)
    assert abs(peak-880)<2 and mapping['sample_zero_media_ms']==1000 and len(data)==16000

def test_ambiguous_mapping_rejected(fixture):
    with pytest.raises(CueError,match='AUDIO_TRACK_MAPPING_AMBIGUOUS'):Media.open(str(fixture),{'mpv_id':1})

def test_external_and_nonlocal_rejected(fixture):
    with pytest.raises(CueError):Media.open(str(fixture),{'external':True})
    with pytest.raises(CueError):local_media('https://example.com/movie.mp4')

def test_late_audio_is_padded(tmp_path):
    path=tmp_path/'late.mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=64x64:r=10:d=4','-itsoffset','1','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=3','-map','0:v','-map','1:a','-c:v','libx264','-c:a','pcm_s16le','-y',str(path)],check=True)
    media=Media.open(str(path),{});dest=tmp_path/'out.wav';extract(media,0,2000,dest)
    data,sr=sf.read(dest)
    assert np.max(np.abs(data[:15000]))==0
    assert np.max(np.abs(data[17000:]))>.01

def test_nonzero_container_origin(tmp_path):
    path=tmp_path/'origin.mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=4','-af','asetpts=PTS+5/TB','-c:a','pcm_s16le','-y',str(path)],check=True)
    media=Media.open(str(path),{});dest=tmp_path/'out.wav';extract(media,1000,2000,dest)
    data,sr=sf.read(dest)
    assert media.origin_seconds==5
    assert np.max(np.abs(data))>.01 and len(data)==16000

def test_source_change_invalidates(fixture):
    media=Media.open(str(fixture),{'ff_index':1})
    assert media.unchanged()
    altered=Media(**{**media.__dict__,'size':media.size+1})
    assert not altered.unchanged()
