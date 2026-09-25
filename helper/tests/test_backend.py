import pytest
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
    def send(prompt,max_tokens,schema=None):
        requests.append(prompt)
        return '[{"id":"2","text":"再見"},{"id":"1","text":"你好"}]'
    backend.send=send
    source=[Cue('a'*24,100,200,'hello'),Cue('b'*24,300,400,'goodbye')]
    assert backend.translate(source,'zh-TW','en')==[Cue('a'*24,100,200,'你好'),Cue('b'*24,300,400,'再見')]
    assert 'a'*24 not in requests[0]

def test_numeric_cue_does_not_require_chinese_characters(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None:'[{"id":"1","text":"這是十四"},{"id":"2","text":"14"}]'
    source=[Cue('a'*24,100,200,'That is fourteen'),Cue('b'*24,300,400,'14')]
    assert backend.translate(source,'zh-TW','en')==[Cue('a'*24,100,200,'這是十四'),Cue('b'*24,300,400,'14')]

def test_wholly_untranslated_speech_batch_still_fails(tmp_path):
    from pytest import raises
    from cue.core import CueError
    backend=Backend(tmp_path)
    requests=[]
    def send(prompt,max_tokens,schema=None):
        requests.append(prompt)
        if len(ids_in(prompt))==2: return '[{"id":"1","text":"That is fourteen"},{"id":"2","text":"14"}]'
        return '[{"id":"1","text":"That is fourteen"}]' if 'fourteen' in prompt else '[{"id":"1","text":"14"}]'
    backend.send=send
    with raises(CueError,match='target script absent'):
        backend.translate([Cue('a'*24,100,200,'That is fourteen'),Cue('b'*24,300,400,'14')],'zh-TW','en')
    # One batch request, then one request per cue, none of them the first prompt again.
    assert len(requests)==3 and requests[0] not in requests[1:]

def test_japanese_and_korean_output_keep_ids_and_measured_times(tmp_path):
    backend=Backend(tmp_path)
    source=[Cue('stable',100,400,'Good morning')]
    for target, text, prompt_name in [('ja','おはようございます','Japanese'),('ko','좋은 아침입니다','Korean')]:
        prompts=[]
        def send(prompt,max_tokens,schema=None):
            prompts.append(prompt)
            return json.dumps([{'id':'1','text':text}],ensure_ascii=False)
        backend.send=send
        assert backend.translate(source,target,'en')==[Cue('stable',100,400,text)]
        assert f'Translate every subtitle into {prompt_name}' in prompts[0]

def test_japanese_and_korean_reject_untranslated_speech_batch(tmp_path):
    from pytest import raises
    from cue.core import CueError
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None:'[{"id":"1","text":"Good morning"}]'
    for target in ('ja','ko'):
        with raises(CueError,match='target script absent'):
            backend.translate([Cue('stable',100,400,'Good morning')],target,'en')

def test_simplified_chinese_is_distinct_from_chinese_source_and_keeps_timing(tmp_path):
    backend=Backend(tmp_path)
    prompts=[]
    def send(prompt,max_tokens,schema=None):
        prompts.append(prompt)
        return '[{"id":"1","text":"火车明天早上九点出发。"}]'
    backend.send=send
    source=[Cue('stable',100,400,'火車明天早上九點出發。')]
    assert backend.translate(source,'zh-CN','zh')==[Cue('stable',100,400,'火车明天早上九点出发。')]
    assert 'Simplified Chinese' in prompts[0]
    assert 'simplified characters' in prompts[0]


def translating_backend(tmp_path,answers):
    """answers(prompt, schema) returns raw model text; every call is recorded."""
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None):
        calls.append((prompt,schema));return answers(prompt,schema)
    backend.send=send
    return backend,calls

def ids_in(prompt):
    return [row['id'] for row in __import__('json').loads(prompt[prompt.index('\n[')+1:])]

def test_translation_is_constrained_to_one_object_per_cue_in_order(tmp_path):
    backend,calls=translating_backend(tmp_path,lambda p,s:'[{"id":"1","text":"你好"},{"id":"2","text":"再見"}]')
    backend.translate([Cue('a',0,1,'Hello'),Cue('b',2,3,'Bye')],'zh-TW','en')
    schema=calls[0][1]
    assert [item['properties']['id']['const'] for item in schema['prefixItems']]==['1','2']
    assert schema['minItems']==schema['maxItems']==2 and schema['items'] is False
    assert schema['prefixItems'][0]['properties']['text']['minLength']==1
    assert 'pattern' not in schema['prefixItems'][0]['properties']['text']

def test_kana_in_chinese_output_is_retried_cue_by_cue_with_a_different_prompt(tmp_path):
    def answers(prompt,schema):
        if len(ids_in(prompt))==2: return '[{"id":"1","text":"請給我一個コロッケ"},{"id":"2","text":"好的"}]'
        return '[{"id":"1","text":"請給我一個可樂餅"}]' if 'コロッケ' in prompt else '[{"id":"1","text":"好的"}]'
    backend,calls=translating_backend(tmp_path,answers)
    out=backend.translate([Cue('a',0,1,'コロッケ ください'),Cue('b',2,3,'はい')],'zh-TW','ja')
    assert [c.text for c in out]==['請給我一個可樂餅','好的']
    first=calls[0][0]
    assert len(calls)==3 and all(prompt!=first for prompt,_ in calls[1:])
    assert all(schema['prefixItems'][0]['properties']['text']['pattern']=='^[^\u3040-\u30ff]+$' for _,schema in calls[1:])

def test_broken_json_is_recovered_by_the_per_cue_retry(tmp_path):
    def answers(prompt,schema):
        if len(ids_in(prompt))==2: return '[{"id":"1","text":"看來，"},{"id":"2","text":"老人家獨居，" "說真的，"}]'
        return '[{"id":"1","text":"看來，"}]' if 'ほら' in prompt else '[{"id":"1","text":"老人家獨居，"}]'
    backend,calls=translating_backend(tmp_path,answers)
    out=backend.translate([Cue('a',0,1,'ほら 、'),Cue('b',2,3,'お 年寄り の 1人暮らし')],'zh-TW','ja')
    assert [c.text for c in out]==['看來，','老人家獨居，'] and len(calls)==3

def test_kana_that_survives_the_retry_fails_the_window(tmp_path):
    backend,_=translating_backend(tmp_path,lambda p,s:'[{"id":"1","text":"請給我コロッケ"}]')
    with pytest.raises(CueError) as exc:
        backend.translate([Cue('a',0,1,'コロッケ ください')],'zh-TW','ja')
    assert exc.value.code=='TRANSLATION_FAILED'

def test_korean_rejects_kana_and_japanese_keeps_it(tmp_path):
    backend,_=translating_backend(tmp_path,lambda p,s:'[{"id":"1","text":"안녕 コロッケ"}]')
    with pytest.raises(CueError):
        backend.translate([Cue('a',0,1,'Hello croquette')],'ko','en')
    backend,calls=translating_backend(tmp_path,lambda p,s:'[{"id":"1","text":"こんにちは"}]')
    assert backend.translate([Cue('a',0,1,'Hello')],'ja','en')[0].text=='こんにちは'
    assert len(calls)==1

def test_a_name_only_cue_may_stay_in_latin_letters_after_the_retry(tmp_path):
    def answers(prompt,schema):
        if len(ids_in(prompt))==2: return 'not json'
        return '[{"id":"1","text":"Yuri"}]' if 'ゆり' in prompt else '[{"id":"1","text":"她叫什麼？"}]'
    backend,_=translating_backend(tmp_path,answers)
    out=backend.translate([Cue('a',0,1,'ゆり'),Cue('b',2,3,'名前 は ?')],'zh-TW','ja')
    assert [c.text for c in out]==['Yuri','她叫什麼？']
