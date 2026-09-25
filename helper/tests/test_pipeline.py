import pytest
from dataclasses import asdict
import numpy as np
import soundfile as sf
from cue.core import CueError, Settings, Unit
from cue.media import Media
from cue.pipeline import Pipeline

class StubVad:
    """Answers the pipeline's speech question without the Silero model."""
    def __init__(self,speech=True):
        self.speech=speech; self.calls=0
    def has_speech(self,audio):
        self.calls+=1
        return self.speech,{'vad_max_prob':.9 if self.speech else .02,'vad_speech_ms':500 if self.speech else 0}

def setup_pipeline(monkeypatch,tmp_path,silent=False,speech=True):
    def extract(media,start,end,dest):
        samples=np.zeros((end-start)*16,dtype='float32') if silent else np.full((end-start)*16,.01,dtype='float32')
        sf.write(dest,samples,16000,subtype='FLOAT')
        return {'sample_count':len(samples),'sample_zero_media_ms':start}
    monkeypatch.setattr('cue.pipeline.extract',extract)
    p=Pipeline(tmp_path/'models',tmp_path/'temp')
    class Backend:
        calls=[]
        def load(self): self.calls.append('load')
        def transcribe(self,a,source='auto'):self.calls.append(('asr',source));return 'one two'
        def language(self,t,s):return {'code':'en','status':'manual'}
        def align(self,a,t,l,partial=False):
            self.calls.append('align');units=[Unit(500,800,'one'),Unit(8500,9500,'two')]
            return (units,None) if partial else units
        def translate(self,c,t,l):self.calls.append('translate');return c
    p.backend=Backend()
    p.vad=StubVad(speech)
    job={'media':asdict(Media('/fixture','s',1,'key',30000,0,1,1)),
         'settings':asdict(Settings(target='original')),'range':[0,10000],'source_profile':'p'}
    return p,job

def test_unresolved_word_does_not_advance_coverage(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    result=p.run(job)
    assert result['committed_range']==[0,8500]
    assert [c['text'] for c in result['source']]==['one']

def test_cached_source_skips_asr_and_alignment(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['cached_source']={'cues':[{'id':'stable','start_ms':500,'end_ms':800,'text':'hello'}],'language':{'code':'en'}}
    result=p.run(job)
    assert p.backend.calls==['load','translate']
    assert result['committed_range']==[0,10000]

def test_pipeline_restores_asr_sentence_breaks_lost_by_aligner(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.transcribe=lambda audio,source='auto':'Hello world. Next sentence.'
    p.backend.align=lambda audio,text,language,partial=False:([
        Unit(500,800,'Hello'),Unit(850,1200,'world'),Unit(1250,1600,'Next'),Unit(1650,2000,'sentence')],None)
    result=p.run(job)
    assert [c['text'] for c in result['source']]==['Hello world.','Next sentence.']
    assert [(c['start_ms'],c['end_ms']) for c in result['source']]==[(500,1200),(1250,2000)]
    assert result['timings']['transcript_punctuation_restored'] is True

def test_exact_silence_requires_no_model(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,True)
    result=p.run(job)
    assert p.backend.calls==[]
    assert result['coverage_kind']=='verified_no_speech'
    assert result['source']==[] and result['committed_range']==[0,10000]

def test_existing_right_coverage_seals_draft_without_reprocessing_forever(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    job['following_source']=[{'id':'next','start_ms':10500,'end_ms':11500,'text':'next'}]
    result=p.run(job)
    assert result['committed_range']==[0,10000]
    assert [c['text'] for c in result['source']]==['one','two']

def test_crossing_word_at_cached_right_edge_is_not_given_an_invented_end(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.transcribe=lambda audio,source='auto':'one different draft'
    p.backend.align=lambda audio,text,language,partial=False:([Unit(500,800,'one'),Unit(8500,10500,'different draft')],None)
    job['following_source']=[{'id':'next','start_ms':10500,'end_ms':11500,'text':'already cached'}]
    result=p.run(job)
    assert result['committed_range']==[0,10000]
    assert [c['text'] for c in result['source']]==['one']
    assert result['timings']['boundary_discarded_units']==1

def test_unsupported_auto_lid_retries_without_loading_aligner(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.language=lambda text,source:{'code':'pl','status':'tentative','method':'original_asr_text_lid'}
    progress=[]
    try:
        p.run(job,lambda stage,language=None:progress.append((stage,language)))
    except CueError as exc:
        assert exc.code=='LANGUAGE_UNCERTAIN'
    else:
        assert False, 'unsupported auto LID must remain uncertain'
    assert p.backend.calls==['load',('asr','auto')]
    assert progress[-1][1]['code']=='pl'


def test_window_without_speech_skips_asr_and_is_verified_no_speech(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,speech=False)
    result=p.run(job)
    assert p.backend.calls==[]
    assert p.vad.calls==1
    assert result['coverage_kind']=='verified_no_speech'
    assert result['committed_range']==[0,10000]
    assert result['source']==[] and result['rendered']==[]
    assert result['language']=={'code':'und','status':'unknown','method':'voice_activity'}
    assert result['timings']['vad_speech_ms']==0

def test_window_with_speech_goes_through_asr_as_before(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,speech=True)
    result=p.run(job)
    assert p.vad.calls==1
    assert ('asr','auto') in p.backend.calls
    assert result['coverage_kind']=='complete'

def test_digital_silence_needs_no_voice_activity_model(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,silent=True)
    result=p.run(job)
    assert p.vad.calls==0
    assert result['coverage_kind']=='verified_no_speech'

def test_cached_transcript_is_not_checked_again(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path,speech=False)
    job['cached_source']={'cues':[{'id':'stable','start_ms':500,'end_ms':800,'text':'hello'}],'language':{'code':'en'}}
    result=p.run(job)
    assert p.vad.calls==0
    assert result['coverage_kind']=='complete'

def test_missing_voice_activity_model_is_a_setup_error(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.vad=None
    p.vad_model=tmp_path/'missing.onnx'
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='SETUP_REQUIRED'
    assert p.backend.calls==[]


def test_a_collapsed_window_commits_its_aligned_part_and_leaves_the_rest_for_the_next(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    # Transcript "one two three": the aligner placed "one two"; "three" collapsed at 6.2 s of the span.
    p.backend.transcribe=lambda a,source='auto':'one two three'
    p.backend.align=lambda a,t,l,partial=False:([Unit(500,800,'one'),Unit(1500,1900,'two')],6200)
    result=p.run(job)
    # The span starts at 0 here, so the cut is at 6.2 s of media time.
    assert result['committed_range']==[0,6200]
    assert [c['text'] for c in result['source']]==['one','two']
    assert result['timings']['alignment_cut_ms']==6200
    boundaries={0+t for u in [Unit(500,800,''),Unit(1500,1900,'')] for t in (u.start_ms,u.end_ms)}
    assert all(c['start_ms'] in boundaries and c['end_ms'] in boundaries for c in result['source'])

def test_too_little_before_the_collapse_fails_the_window_as_before(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.transcribe=lambda a,source='auto':'one two'
    p.backend.align=lambda a,t,l,partial=False:([Unit(500,800,'one')],1500)
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='ALIGNMENT_FAILED'

def test_nothing_aligned_before_the_collapse_fails_the_window(monkeypatch,tmp_path):
    p,job=setup_pipeline(monkeypatch,tmp_path)
    p.backend.align=lambda a,t,l,partial=False:([],300)
    with pytest.raises(CueError) as exc:
        p.run(job)
    assert exc.value.code=='ALIGNMENT_FAILED'
