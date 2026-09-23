import json
import sys
from types import SimpleNamespace
from cue.backend import Backend, LANGUAGES
from cue.core import Cue, CueError, SOURCE_LANGUAGES

def test_backend_maps_every_allowed_source_to_the_pinned_aligner_name():
    assert LANGUAGES is SOURCE_LANGUAGES

def test_manual_source_guides_transcription_without_translation(tmp_path):
    backend=Backend(tmp_path)
    prompts=[]
    backend.send=lambda prompt,audio: prompts.append(prompt) or 'Buenos días, ¿cómo estás?'
    assert backend.transcribe(tmp_path/'sample.wav','es')=='Buenos días, ¿cómo estás?'
    assert 'in Spanish into Spanish text' in prompts[0]
    assert 'Do not translate' in prompts[0]
    assert backend.language('anything','es')['code']=='es'

def test_cold_language_detection_does_not_load_aligner(tmp_path,monkeypatch):
    (tmp_path/'gemma').mkdir(); (tmp_path/'aligner').mkdir()
    (tmp_path/'gemma/gemma-4-E2B-it.litertlm').touch()
    (tmp_path/'aligner/model.safetensors').touch()
    engine=SimpleNamespace(close=lambda:None)
    gpu=SimpleNamespace(GPU=lambda:'gpu',CPU=lambda:'cpu')
    monkeypatch.setitem(sys.modules,'litert_lm',SimpleNamespace(
        set_min_log_severity=lambda severity:None,LogSeverity=SimpleNamespace(ERROR=1),
        Engine=lambda *args,**kwargs:engine,Backend=gpu))
    backend=Backend(tmp_path); backend.load()
    assert backend.engine is engine and backend.aligner is None
    language=backend.language('Καλημέρα σας, θέλω να μιλήσουμε για αυτή την ταινία.','auto')
    assert language['code']=='el' and language['status']=='tentative'
    try:
        backend.align(tmp_path/'audio.wav','Καλημέρα',language['code'])
    except CueError as exc:
        assert exc.code=='ALIGNMENT_LANGUAGE_UNSUPPORTED'
    else: raise AssertionError('Greek must not be given unsupported timestamps')
    assert backend.aligner is None
    backend.close()

def test_short_translation_aliases_restore_stable_ids_and_measured_times(tmp_path):
    backend=Backend(tmp_path)
    requests=[]
    def send(prompt,max_tokens):
        requests.append(prompt)
        return '[{"id":"2","text":"再見"},{"id":"1","text":"你好"}]'
    backend.send=send
    source=[Cue('a'*24,100,200,'hello'),Cue('b'*24,300,400,'goodbye')]
    assert backend.translate(source,'zh-TW','en')==[Cue('a'*24,100,200,'你好'),Cue('b'*24,300,400,'再見')]
    assert 'a'*24 not in requests[0]

def test_numeric_cue_does_not_require_chinese_characters(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens:'[{"id":"1","text":"這是十四"},{"id":"2","text":"14"}]'
    source=[Cue('a'*24,100,200,'That is fourteen'),Cue('b'*24,300,400,'14')]
    assert backend.translate(source,'zh-TW','en')==[Cue('a'*24,100,200,'這是十四'),Cue('b'*24,300,400,'14')]

def test_wholly_untranslated_speech_batch_still_fails(tmp_path):
    from pytest import raises
    from cue.core import CueError
    backend=Backend(tmp_path)
    requests=[]
    def send(prompt,max_tokens):
        requests.append(prompt)
        return '[{"id":"1","text":"That is fourteen"},{"id":"2","text":"14"}]'
    backend.send=send
    with raises(CueError,match='target script absent'):
        backend.translate([Cue('a'*24,100,200,'That is fourteen'),Cue('b'*24,300,400,'14')],'zh-TW','en')
    assert len(requests)==2

def test_japanese_and_korean_output_keep_ids_and_measured_times(tmp_path):
    backend=Backend(tmp_path)
    source=[Cue('stable',100,400,'Good morning')]
    for target, text, prompt_name in [('ja','おはようございます','Japanese'),('ko','좋은 아침입니다','Korean')]:
        prompts=[]
        def send(prompt,max_tokens):
            prompts.append(prompt)
            return json.dumps([{'id':'1','text':text}],ensure_ascii=False)
        backend.send=send
        assert backend.translate(source,target,'en')==[Cue('stable',100,400,text)]
        assert f'Translate every subtitle into {prompt_name}' in prompts[0]

def test_japanese_and_korean_reject_untranslated_speech_batch(tmp_path):
    from pytest import raises
    from cue.core import CueError
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens:'[{"id":"1","text":"Good morning"}]'
    for target in ('ja','ko'):
        with raises(CueError,match='target script absent'):
            backend.translate([Cue('stable',100,400,'Good morning')],target,'en')

def test_simplified_chinese_is_distinct_from_chinese_source_and_keeps_timing(tmp_path):
    backend=Backend(tmp_path)
    prompts=[]
    def send(prompt,max_tokens):
        prompts.append(prompt)
        return '[{"id":"1","text":"火车明天早上九点出发。"}]'
    backend.send=send
    source=[Cue('stable',100,400,'火車明天早上九點出發。')]
    assert backend.translate(source,'zh-CN','zh')==[Cue('stable',100,400,'火车明天早上九点出发。')]
    assert 'Simplified Chinese' in prompts[0]
    assert 'simplified characters' in prompts[0]
