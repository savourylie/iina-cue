import pytest
from cue.asr import LANGUAGE_NAMES, MlxAsr
from cue.core import CueError

class FakeQwen:
    def __init__(self): self.calls=[]
    def generate(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return type('Out',(),{'text':' Hello, Hansen. '})()

def model_dir(tmp_path, name='qwen', family='qwen3_asr'):
    path=tmp_path/name; path.mkdir(exist_ok=True); (path/'config.json').write_text('{"model_type": "%s"}' % family); return path

def test_mlx_asr_maps_languages_and_passes_a_names_hint(tmp_path):
    fake=FakeQwen()
    asr=MlxAsr(model_dir(tmp_path), loader=lambda path: fake)
    assert asr.transcribe(tmp_path/'a.wav','en')=='Hello, Hansen.'
    assert fake.calls[-1]==(str(tmp_path/'a.wav'),{'language':'English'})
    asr.transcribe(tmp_path/'a.wav','auto',names=['Nash','Hansen'])
    assert fake.calls[-1][1]['language'] is None and 'Nash, Hansen' in fake.calls[-1][1]['system_prompt']
    assert LANGUAGE_NAMES['ja']=='Japanese' and LANGUAGE_NAMES['yue']=='Cantonese' and set(LANGUAGE_NAMES)=={'zh','yue','en','de','es','fr','it','pt','ru','ko','ja'}
    assert asr.key=='mlx-asr:qwen'

def test_mlx_asr_rejects_empty_output_unknown_sources_and_a_model_that_will_not_load(tmp_path):
    class Empty:
        def generate(self, audio, **kwargs): return type('Out',(),{'text':'   '})()
    asr=MlxAsr(model_dir(tmp_path), loader=lambda path: Empty())
    with pytest.raises(CueError) as exc: asr.transcribe(tmp_path/'a.wav','en')
    assert exc.value.code=='ASR_FAILED'
    with pytest.raises(CueError) as exc: asr.transcribe(tmp_path/'a.wav','xx')
    assert exc.value.code=='INVALID_SETTINGS'
    def broken(path): raise RuntimeError('no metal')
    with pytest.raises(CueError) as exc: MlxAsr(model_dir(tmp_path), loader=broken).load()
    assert exc.value.code=='MODEL_LOAD_FAILED'

def test_a_whisper_model_gets_language_codes_timestamps_and_the_previous_text_as_its_prompt(tmp_path):
    fake=FakeQwen()
    asr=MlxAsr(model_dir(tmp_path, 'whisper', 'whisper'), loader=lambda path: fake)
    asr.transcribe(tmp_path/'a.wav','ja')
    # Before anything was heard there is no prompt: Whisper echoed a seed sentence as speech (会話の).
    assert fake.calls[-1][1]=={'language':'ja','return_timestamps':True,'verbose':False}
    earlier='x'*300+' Hansen is used to being picked first.'
    asr.transcribe(tmp_path/'a.wav','auto',names=['Nash','Hansen'],previous=earlier)
    kw=fake.calls[-1][1]
    # Whisper copies its prompt: the tail of what was already heard, never a "Names:" list it would echo.
    assert kw['language'] is None and kw['initial_prompt']==earlier[-220:] and 'Names' not in kw['initial_prompt'] and 'system_prompt' not in kw

def test_qwen_keeps_its_names_hint_and_ignores_the_previous_text(tmp_path):
    fake=FakeQwen(); asr=MlxAsr(model_dir(tmp_path), loader=lambda path: fake)
    asr.transcribe(tmp_path/'a.wav','en',names=['Nash'],previous='Earlier.')
    assert fake.calls[-1][1]['language']=='English' and 'Nash' in fake.calls[-1][1]['system_prompt'] and 'initial_prompt' not in fake.calls[-1][1]

def test_the_model_family_is_read_from_the_config_file(tmp_path):
    (tmp_path/'w').mkdir(); (tmp_path/'w'/'config.json').write_text('{"model_type": "whisper"}')
    (tmp_path/'q').mkdir(); (tmp_path/'q'/'config.json').write_text('{"model_type": "qwen3_asr"}')
    assert MlxAsr(tmp_path/'w', loader=lambda p: FakeQwen()).family=='whisper'
    assert MlxAsr(tmp_path/'q', loader=lambda p: FakeQwen()).family=='qwen3_asr'
    assert MlxAsr(tmp_path/'none', loader=lambda p: FakeQwen()).family=='qwen3_asr'


def test_a_missing_hearing_model_is_setup_required_not_a_load_failure(tmp_path):
    with pytest.raises(CueError) as exc: MlxAsr(tmp_path/'whisper-large-v3-turbo', loader=lambda p: FakeQwen()).load()
    assert exc.value.code=='SETUP_REQUIRED'
    asr=MlxAsr(model_dir(tmp_path, 'whisper-large-v3-turbo', 'whisper'), loader=lambda p: FakeQwen()); asr.load()
    assert asr.model is not None and asr.family=='whisper'

class Decoded:
    """What mlx_audio's Whisper returns: the text and one entry per segment with its decode statistics."""
    def __init__(self, text, temperature, logprob, ratio):
        self.text=text; self.segments=[{'text':text,'temperature':temperature,'avg_logprob':logprob,'compression_ratio':ratio}]

def test_whisper_text_it_did_not_trust_even_at_its_last_temperature_is_a_hearing_failure(tmp_path):
    def whisper(result): return MlxAsr(model_dir(tmp_path,'whisper','whisper'), loader=lambda p: type('M',(),{'generate':lambda self,a,**k: result})())
    # Seen on noisy Tony Takitani audio: Whisper retried up to temperature 1.0 and still had log-probability -5.5.
    for bad in (Decoded('珍口の頭兩osse',1.0,-5.52,0.78), Decoded('はい はい はい はい',1.0,-0.4,2.6)):
        with pytest.raises(CueError) as exc: whisper(bad).transcribe(tmp_path/'a.wav','ja')
        assert exc.value.code=='ASR_FAILED'
    # Accepted by Whisper's own thresholds, at the last temperature or earlier: kept.
    assert whisper(Decoded('雨が降ってきた',1.0,-0.6,1.1)).transcribe(tmp_path/'a.wav','ja')=='雨が降ってきた'
    assert whisper(Decoded('トリーボールを入れて',0.4,-0.85,2.25)).transcribe(tmp_path/'a.wav','ja')=='トリーボールを入れて'
    # Qwen reports no such statistics and is not judged by them.
    qwen=MlxAsr(model_dir(tmp_path), loader=lambda p: type('M',(),{'generate':lambda self,a,**k: Decoded('x',1.0,-9,9)})())
    assert qwen.transcribe(tmp_path/'a.wav','en')=='x'
