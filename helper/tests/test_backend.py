import pytest
import json
import sys
from types import SimpleNamespace
from cue.backend import Backend, LANGUAGES
from cue.core import Cue, CueError, SOURCE_LANGUAGES, TranslationContext

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
    def send(prompt,max_tokens,schema=None,system=None):
        requests.append(prompt)
        return '[{"id":"2","text":"再見"},{"id":"1","text":"你好"}]'
    backend.send=send
    source=[Cue('a'*24,100,200,'hello'),Cue('b'*24,300,400,'goodbye')]
    assert backend.translate(source,'zh-TW','en')[0]==[Cue('a'*24,100,200,'你好'),Cue('b'*24,300,400,'再見')]
    assert 'a'*24 not in requests[0]

def test_numeric_cue_does_not_require_chinese_characters(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'[{"id":"1","text":"這是十四"},{"id":"2","text":"14"}]'
    source=[Cue('a'*24,100,200,'That is fourteen'),Cue('b'*24,300,400,'14')]
    assert backend.translate(source,'zh-TW','en')[0]==[Cue('a'*24,100,200,'這是十四'),Cue('b'*24,300,400,'14')]

def test_wholly_untranslated_speech_batch_still_fails(tmp_path):
    from pytest import raises
    from cue.core import CueError
    backend=Backend(tmp_path)
    requests=[]
    def send(prompt,max_tokens,schema=None,system=None):
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
        def send(prompt,max_tokens,schema=None,system=None):
            prompts.append(prompt)
            return json.dumps([{'id':'1','text':text}],ensure_ascii=False)
        backend.send=send
        assert backend.translate(source,target,'en')[0]==[Cue('stable',100,400,text)]
        assert f'Translate every subtitle into {prompt_name}' in prompts[0]

def test_japanese_and_korean_reject_untranslated_speech_batch(tmp_path):
    from pytest import raises
    from cue.core import CueError
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'[{"id":"1","text":"Good morning"}]'
    for target in ('ja','ko'):
        with raises(CueError,match='target script absent'):
            backend.translate([Cue('stable',100,400,'Good morning')],target,'en')

def test_simplified_chinese_is_distinct_from_chinese_source_and_keeps_timing(tmp_path):
    backend=Backend(tmp_path)
    prompts=[]
    def send(prompt,max_tokens,schema=None,system=None):
        prompts.append(prompt)
        return '[{"id":"1","text":"火车明天早上九点出发。"}]'
    backend.send=send
    source=[Cue('stable',100,400,'火車明天早上九點出發。')]
    assert backend.translate(source,'zh-CN','zh')[0]==[Cue('stable',100,400,'火车明天早上九点出发。')]
    assert 'Simplified Chinese' in prompts[0]
    assert 'simplified characters' in prompts[0]


def translating_backend(tmp_path,answers):
    """answers(prompt, schema) returns raw model text; every call is recorded."""
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
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
    out,_=backend.translate([Cue('a',0,1,'コロッケ ください'),Cue('b',2,3,'はい')],'zh-TW','ja')
    assert [c.text for c in out]==['請給我一個可樂餅','好的']
    first=calls[0][0]
    assert len(calls)==3 and all(prompt!=first for prompt,_ in calls[1:])
    assert all(schema['prefixItems'][0]['properties']['text']['pattern']=='^[^\u3040-\u30ff]+$' for _,schema in calls[1:])

def test_broken_json_is_recovered_by_the_per_cue_retry(tmp_path):
    def answers(prompt,schema):
        if len(ids_in(prompt))==2: return '[{"id":"1","text":"看來，"},{"id":"2","text":"老人家獨居，" "說真的，"}]'
        return '[{"id":"1","text":"看來，"}]' if 'ほら' in prompt else '[{"id":"1","text":"老人家獨居，"}]'
    backend,calls=translating_backend(tmp_path,answers)
    out,_=backend.translate([Cue('a',0,1,'ほら 、'),Cue('b',2,3,'お 年寄り の 1人暮らし')],'zh-TW','ja')
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
    assert backend.translate([Cue('a',0,1,'Hello')],'ja','en')[0][0].text=='こんにちは'
    assert len(calls)==1

def test_a_name_only_cue_may_stay_in_latin_letters_after_the_retry(tmp_path):
    def answers(prompt,schema):
        if len(ids_in(prompt))==2: return 'not json'
        return '[{"id":"1","text":"Yuri"}]' if 'ゆり' in prompt else '[{"id":"1","text":"她叫什麼？"}]'
    backend,_=translating_backend(tmp_path,answers)
    out,_=backend.translate([Cue('a',0,1,'ゆり'),Cue('b',2,3,'名前 は ?')],'zh-TW','ja')
    assert [c.text for c in out]==['Yuri','她叫什麼？']

def test_translation_prompt_carries_context_and_the_system_message_sets_the_register(tmp_path):
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append((prompt,schema,system));return '[{"id":"1","text":"他會追到她。"},{"id":"2","text":"那我們就去追她朋友。"}]'
    backend.send=send
    context=TranslationContext(previous=(("Not a single one of us.","我們沒有一個人。"),),glossary={'Nash':'納許'},variants={'Hanson':'Hansen'},continues=frozenset({'u1'}))
    cues,names=backend.translate([Cue('u1',0,1500,"He's going to get her."),Cue('u2',1600,3200,'So then we go for her friends.')],'zh-TW','en',context)
    prompt,schema,system=calls[0]
    assert 'spoken film dialogue' in system and 'Traditional Chinese' in system and '天啊' in system
    assert 'Established renderings in this film, use them exactly: {"Nash": "納許"}' in prompt
    assert 'Likely misheard names in this batch: Hanson = Hansen' in prompt
    assert '{"source": "Not a single one of us.", "target": "我們沒有一個人。"}' in prompt
    assert 'Subtitle 1 continues the previous subtitle.' in prompt
    assert prompt.index('Established')<prompt.index('Likely')<prompt.index('Previous subtitles')<prompt.index('Subtitle 1')<prompt.index('Translate every')
    assert schema['type']=='array'
    assert names=={} and [c.text for c in cues]==['他會追到她。','那我們就去追她朋友。']
    # The Chinese interjection example is only in the Chinese system messages.
    calls.clear()
    backend.send=lambda prompt,max_tokens,schema=None,system=None: calls.append((prompt,schema,system)) or '[{"id":"1","text":"やあ"}]'
    backend.translate([Cue('u1',0,1,'Hi')],'ja','en')
    assert '天啊' not in calls[0][2] and 'Japanese' in calls[0][2]

def test_new_names_are_requested_in_a_constrained_object_and_kept_only_when_used(tmp_path):
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append((prompt,schema))
        return '{"cues":[{"id":"1","text":"漢森先生，謝謝。"},{"id":"2","text":"索爾在這裡。"}],"names":{"Hanson":"漢森","Saw":"薩爾"}}'
    backend.send=send
    cues,names=backend.translate([Cue('a',0,1,'Thank you, Mr. Hanson.'),Cue('b',2,3,'Saw is here.')],'zh-TW','en',TranslationContext(new_names=('Hanson','Saw')))
    prompt,schema=calls[0]
    assert 'report the rendering you used for each in "names": ["Hanson", "Saw"]' in prompt
    assert 'Return ONLY a JSON object with "cues" and "names"' in prompt
    assert schema['type']=='object' and schema['required']==['cues','names']
    assert schema['properties']['names']['required']==['Hanson','Saw']
    assert schema['properties']['names']['properties']['Saw']=={'type':'string','minLength':1,'maxLength':16,'pattern':'^[㐀-鿿·]+$'}
    assert schema['properties']['cues']['prefixItems'][1]['properties']['id']['const']=='2'
    assert [c.text for c in cues]==['漢森先生，謝謝。','索爾在這裡。']
    assert names=={'Hanson':'漢森'}

def test_names_are_requested_only_in_the_batch_where_they_occur(tmp_path):
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append(schema)
        if schema['type']=='array':
            return json.dumps([{"id":str(i+1),"text":f"譯{i+1}"} for i in range(schema['minItems'])])
        return '{"cues":[{"id":"1","text":"納許來了"}],"names":{"Nash":"納許"}}'
    backend.send=send
    units=[Cue(f'u{i}',i*100,i*100+90,f'line {i}') for i in range(12)]+[Cue('u12',1200,1290,'Nash is here.')]
    cues,names=backend.translate(units,'zh-TW','en',TranslationContext(new_names=('Nash',)))
    assert [s['type'] for s in calls]==['array','object'] and names=={'Nash':'納許'} and len(cues)==13

def test_the_per_cue_retry_keeps_the_context_but_asks_for_no_names(tmp_path):
    backend=Backend(tmp_path);calls=[]
    replies=iter(['not json','[{"id":"1","text":"納許來了"}]','[{"id":"1","text":"漢森走了"}]'])
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append((prompt,schema));return next(replies)
    backend.send=send
    context=TranslationContext(previous=(("Before.","之前。"),),new_names=('Nash','Hansen'))
    cues,names=backend.translate([Cue('a',0,1,'Nash came.'),Cue('b',2,3,'Hansen left.')],'zh-TW','en',context)
    assert calls[0][1]['type']=='object'
    assert all(s['type']=='array' and 'pattern' in s['prefixItems'][0]['properties']['text'] for _,s in calls[1:])
    assert all('之前。' in p and '"names"' not in p for p,_ in calls[1:])
    assert names=={} and [c.text for c in cues]==['納許來了','漢森走了']

def test_a_broken_names_object_keeps_the_cues(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'{"cues":[{"id":"1","text":"納許來了"}],"names":"納許"}'
    cues,names=backend.translate([Cue('a',0,1,'Nash came.')],'zh-TW','en',TranslationContext(new_names=('Nash',)))
    assert [c.text for c in cues]==['納許來了'] and names=={}

def test_transcription_gets_a_names_hint_only_when_names_are_known(tmp_path):
    backend=Backend(tmp_path);prompts=[]
    backend.send=lambda prompt,audio: prompts.append(prompt) or 'Hello Hansen.'
    backend.transcribe(tmp_path/'a.wav','en')
    backend.transcribe(tmp_path/'a.wav','en',names=['Nash','Hansen'])
    assert 'Proper names' not in prompts[0]
    assert prompts[1].endswith(' Proper names that may be spoken, spell them this way if heard: Nash, Hansen.')
