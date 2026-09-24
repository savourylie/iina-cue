import subprocess
import errno
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from cue.core import CueError
from cue.media import Media, binary, extract, local_media, probe, select_stream
from cue.remux import _duration_seconds, _progress_percent, remux

@pytest.fixture(scope='session')
def fixture(tmp_path_factory):
    root=tmp_path_factory.mktemp('media')
    path=root/'多音軌 $test; "quote".mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=64x64:r=10:d=4','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=4','-f','lavfi','-i','sine=frequency=880:sample_rate=16000:duration=4','-map','0:v','-map','1:a','-map','2:a','-c:v','mpeg4','-bf','0','-c:a','pcm_s16le','-metadata:s:a:0','language=eng','-metadata:s:a:1','language=jpn','-y',str(path)],check=True)
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
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=64x64:r=10:d=4','-itsoffset','1','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=3','-map','0:v','-map','1:a','-c:v','mpeg4','-bf','0','-c:a','pcm_s16le','-y',str(path)],check=True)
    media=Media.open(str(path),{});dest=tmp_path/'out.wav';extract(media,0,2000,dest)
    data,sr=sf.read(dest)
    assert np.max(np.abs(data[:15000]))==0
    assert np.max(np.abs(data[17000:]))>.01
    copy=tmp_path/'late-remux.mkv';remux(str(path),str(copy))
    starts={s['codec_type']:float(s['start_time']) for s in probe(copy)['streams']}
    assert abs((starts['audio']-starts['video'])-1)<.1

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

def test_remux_keeps_original_and_copies_every_stream(fixture,tmp_path):
    before=fixture.stat()
    output=tmp_path/'timestamp fixed.mkv'
    updates=[]
    assert remux(str(fixture),str(output),lambda phase,percent:updates.append((phase,percent)))==str(output)
    assert any(phase=='copying' and percent is not None and percent>0 for phase,percent in updates)
    assert ('verifying',99) in updates and ('saving',99) in updates
    assert all(percent is None or 0<=percent<=99 for _,percent in updates)
    assert fixture.stat().st_size==before.st_size and fixture.stat().st_mtime_ns==before.st_mtime_ns
    original=probe(fixture); copied=probe(output)
    assert sorted((s['codec_type'],s['codec_name']) for s in original['streams'])==sorted((s['codec_type'],s['codec_name']) for s in copied['streams'])
    assert abs(float(original['format']['duration'])-float(copied['format']['duration']))<.25
    assert abs(min(float(s['start_time']) for s in copied['streams']))<.1
    with pytest.raises(CueError,match='OUTPUT_EXISTS'):remux(str(fixture),str(output))
    with pytest.raises(CueError):remux(str(fixture),str(fixture))

def test_remux_cancel_stops_ffmpeg_and_leaves_no_files(fixture,tmp_path,monkeypatch):
    import threading,time
    before=fixture.stat()
    # A stand-in FFmpeg that would run for a minute proves cancellation terminates it.
    slow=tmp_path/'slow-ffmpeg';slow.write_text('#!/bin/sh\nexec sleep 60\n');slow.chmod(0o755)
    monkeypatch.setattr('cue.remux.binary',lambda name:str(slow) if name=='ffmpeg' else binary(name))
    cancel=threading.Event()
    output=tmp_path/'cancelled.mkv'
    def progress(phase,percent):
        if phase=='copying':cancel.set()
    started=time.monotonic()
    with pytest.raises(CueError,match='REMUX_CANCELLED'):remux(str(fixture),str(output),progress,cancel)
    assert time.monotonic()-started<5
    assert not output.exists()
    assert not list(tmp_path.glob('.cue-remux-*'))
    assert fixture.stat().st_size==before.st_size and fixture.stat().st_mtime_ns==before.st_mtime_ns

def test_remux_cancel_before_start_writes_nothing(fixture,tmp_path):
    import threading
    cancel=threading.Event();cancel.set()
    output=tmp_path/'never.mkv'
    with pytest.raises(CueError,match='REMUX_CANCELLED'):remux(str(fixture),str(output),None,cancel)
    assert not output.exists() and not list(tmp_path.glob('.cue-remux-*'))

def test_remux_progress_uses_ffmpeg_microseconds_and_stays_below_completion():
    assert _progress_percent({'out_time_us':'2500000'},10)==25
    assert _progress_percent({'out_time_ms':'2500000'},10)==25
    assert _progress_percent({'out_time':'00:00:02.500000'},10)==25
    assert _progress_percent({'out_time_us':'15000000'},10)==99
    assert _progress_percent({'out_time_us':'N/A'},10) is None

def test_remux_shifts_nonzero_origin_to_zero(tmp_path):
    source=tmp_path/'offset.mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=2',
                    '-af','asetpts=PTS+5/TB','-c:a','pcm_s16le','-y',str(source)],check=True)
    source_info=probe(source)
    assert float(source_info['streams'][0]['start_time'])==5
    assert abs(_duration_seconds(source_info)-2)<.1
    output=tmp_path/'offset fixed.mkv'
    remux(str(source),str(output))
    assert abs(float(probe(output)['streams'][0]['start_time']))<.1

def test_binary_override_does_not_fall_back(tmp_path,monkeypatch):
    bindir=tmp_path/'bin'
    bindir.mkdir()
    ffmpeg=bindir/'ffmpeg'
    ffmpeg.write_text('not a real ffmpeg\n')
    monkeypatch.setenv('CUE_FFMPEG_BIN_DIR',str(bindir))
    assert binary('ffmpeg')==str(ffmpeg)
    with pytest.raises(CueError,match='ffprobe unavailable'):binary('ffprobe')

def test_remux_on_disk_without_hard_links_does_not_replace_racing_output(fixture,tmp_path,monkeypatch):
    output=tmp_path/'copy.mkv'
    def unsupported(source,destination):
        output.write_text('another file won the name')
        raise OSError(errno.ENOTSUP,'hard links unavailable')
    with monkeypatch.context() as patch:
        patch.setattr('cue.remux.os.link',unsupported)
        with pytest.raises(CueError,match='OUTPUT_EXISTS'):remux(str(fixture),str(output))
    assert output.read_text()=='another file won the name'
    output.unlink()
    def no_links(*_):raise OSError(errno.ENOTSUP,'hard links unavailable')
    with monkeypatch.context() as patch:
        patch.setattr('cue.remux.os.link',no_links)
        remux(str(fixture),str(output))
    assert len(probe(output)['streams'])==3
