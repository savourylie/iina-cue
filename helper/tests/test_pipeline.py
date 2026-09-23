from dataclasses import asdict
import numpy as np
import soundfile as sf
from cue.core import Settings, Unit
from cue.media import Media
from cue.pipeline import Pipeline

def setup_pipeline(monkeypatch,tmp_path,silent=False):
    def extract(media,start,end,dest):
        samples=np.zeros((end-start)*16,dtype='float32') if silent else np.full((end-start)*16,.01,dtype='float32')
        sf.write(dest,samples,16000,subtype='FLOAT')
        return {'sample_count':len(samples),'sample_zero_media_ms':start}
    monkeypatch.setattr('cue.pipeline.extract',extract)
    p=Pipeline(tmp_path/'models',tmp_path/'temp')
    class Backend:
        calls=[]
        def load(self): self.calls.append('load')
        def transcribe(self,a):self.calls.append('asr');return 'one two'
        def language(self,t,s):return {'code':'en','status':'manual'}
        def align(self,a,t,l):self.calls.append('align');return [Unit(500,800,'one'),Unit(8500,9500,'two')]
        def translate(self,c,t,l):self.calls.append('translate');return c
    p.backend=Backend()
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
    p.backend.transcribe=lambda audio:'one different draft'
    p.backend.align=lambda audio,text,language:[Unit(500,800,'one'),Unit(8500,10500,'different draft')]
    job['following_source']=[{'id':'next','start_ms':10500,'end_ms':11500,'text':'already cached'}]
    result=p.run(job)
    assert result['committed_range']==[0,10000]
    assert [c['text'] for c in result['source']]==['one']
    assert result['timings']['boundary_discarded_units']==1
