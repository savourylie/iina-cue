import pytest
from cue.asr import LANGUAGE_NAMES, MlxAsr
from cue.core import CueError

class FakeQwen:
    def __init__(self): self.calls=[]
    def generate(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return type('Out',(),{'text':' Hello, Hansen. '})()

def test_mlx_asr_maps_languages_and_passes_a_names_hint(tmp_path):
    fake=FakeQwen()
    asr=MlxAsr(tmp_path/'qwen', loader=lambda path: fake)
    assert asr.transcribe(tmp_path/'a.wav','en')=='Hello, Hansen.'
    assert fake.calls[-1]==(str(tmp_path/'a.wav'),{'language':'English'})
    asr.transcribe(tmp_path/'a.wav','auto',names=['Nash','Hansen'])
    assert fake.calls[-1][1]['language'] is None and 'Nash, Hansen' in fake.calls[-1][1]['system_prompt']
    assert LANGUAGE_NAMES['ja']=='Japanese' and LANGUAGE_NAMES['yue']=='Cantonese' and set(LANGUAGE_NAMES)=={'zh','yue','en','de','es','fr','it','pt','ru','ko','ja'}
    assert asr.key=='mlx-asr:qwen'

def test_mlx_asr_rejects_empty_output_unknown_sources_and_a_model_that_will_not_load(tmp_path):
    class Empty:
        def generate(self, audio, **kwargs): return type('Out',(),{'text':'   '})()
    asr=MlxAsr(tmp_path/'qwen', loader=lambda path: Empty())
    with pytest.raises(CueError) as exc: asr.transcribe(tmp_path/'a.wav','en')
    assert exc.value.code=='ASR_FAILED'
    with pytest.raises(CueError) as exc: asr.transcribe(tmp_path/'a.wav','xx')
    assert exc.value.code=='INVALID_SETTINGS'
    def broken(path): raise RuntimeError('no metal')
    with pytest.raises(CueError) as exc: MlxAsr(tmp_path/'qwen', loader=broken).load()
    assert exc.value.code=='MODEL_LOAD_FAILED'

def test_a_whisper_model_gets_language_codes_timestamps_and_the_previous_text_as_its_prompt(tmp_path):
    fake=FakeQwen()
    asr=MlxAsr(tmp_path/'whisper', loader=lambda path: fake, family='whisper')
    asr.transcribe(tmp_path/'a.wav','ja')
    # Without earlier text, a punctuated seed in the source language keeps the output cased and punctuated.
    assert fake.calls[-1][1]=={'language':'ja','return_timestamps':True,'verbose':False,'initial_prompt':'会話の書き起こし。'}
    earlier='x'*300+' Hansen is used to being picked first.'
    asr.transcribe(tmp_path/'a.wav','auto',names=['Nash','Hansen'],previous=earlier)
    kw=fake.calls[-1][1]
    # Whisper copies its prompt: the tail of what was already heard, never a "Names:" list it would echo.
    assert kw['language'] is None and kw['initial_prompt']==earlier[-220:] and 'Names' not in kw['initial_prompt'] and 'system_prompt' not in kw
    from cue.asr import WHISPER_PROMPTS
    from cue.core import SOURCE_LANGUAGES
    assert set(WHISPER_PROMPTS)==set(SOURCE_LANGUAGES) and all(p.rstrip()[-1] in '.。' for p in WHISPER_PROMPTS.values())

def test_qwen_keeps_its_names_hint_and_ignores_the_previous_text(tmp_path):
    fake=FakeQwen(); asr=MlxAsr(tmp_path/'qwen', loader=lambda path: fake, family='qwen3_asr')
    asr.transcribe(tmp_path/'a.wav','en',names=['Nash'],previous='Earlier.')
    assert fake.calls[-1][1]['language']=='English' and 'Nash' in fake.calls[-1][1]['system_prompt'] and 'initial_prompt' not in fake.calls[-1][1]

def test_the_model_family_is_read_from_the_config_file(tmp_path):
    (tmp_path/'w').mkdir(); (tmp_path/'w'/'config.json').write_text('{"model_type": "whisper"}')
    (tmp_path/'q').mkdir(); (tmp_path/'q'/'config.json').write_text('{"model_type": "qwen3_asr"}')
    assert MlxAsr(tmp_path/'w', loader=lambda p: FakeQwen()).family=='whisper'
    assert MlxAsr(tmp_path/'q', loader=lambda p: FakeQwen()).family=='qwen3_asr'
    assert MlxAsr(tmp_path/'none', loader=lambda p: FakeQwen()).family=='qwen3_asr'
