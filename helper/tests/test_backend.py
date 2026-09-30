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
    assert schema['properties']['names']['properties']['Saw']=={'type':'string','minLength':1,'maxLength':16,'pattern':'^[\u3400-\u9fff]+$'}
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

def test_multi_word_names_get_space_free_schema_keys_and_map_back(tmp_path):
    # The constrained decoder forces JSON keys byte by byte, and this tokenizer writes a
    # space as ▁, so a key with a space can never be emitted. Keys use underscores instead.
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append((prompt,schema));return '{"cues":[{"id":"1","text":"他在惠勒實驗室。"}],"names":{"Wheeler_Labs":"惠勒實驗室"}}'
    backend.send=send
    cues,names=backend.translate([Cue('a',0,1,'He is at Wheeler Labs.')],'zh-TW','en',TranslationContext(new_names=('Wheeler Labs',)))
    prompt,schema=calls[0]
    assert list(schema['properties']['names']['properties'])==['Wheeler_Labs'] and schema['properties']['names']['required']==['Wheeler_Labs']
    assert '"names": ["Wheeler Labs"]' in prompt
    assert names=={'Wheeler Labs':'惠勒實驗室'} and [c.text for c in cues]==['他在惠勒實驗室。']

def test_an_engine_error_on_the_names_call_falls_back_to_the_per_cue_retry(tmp_path):
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append(schema['type'])
        if schema['type']=='object': raise RuntimeError('Parser Error: token doesn\'t satisfy the grammar')
        return '[{"id":"1","text":"納許來了"}]'
    backend.send=send
    cues,names=backend.translate([Cue('a',0,1,'Nash came.')],'zh-TW','en',TranslationContext(new_names=('Nash',)))
    assert calls==['object','array'] and names=={} and [c.text for c in cues]==['納許來了']

def test_a_rendering_shared_by_two_requested_names_stays_with_the_longest_spelling(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'{"cues":[{"id":"1","text":"見到約翰·納什。"}],"names":{"John_Nash":"約翰·納什","Nash":"約翰·納什"}}'
    cues,names=backend.translate([Cue('a',0,1,'Meet John Nash.')],'zh-TW','en',TranslationContext(new_names=('John Nash','Nash')))
    assert names=={'John Nash':'約翰·納什'}

def test_a_rendering_already_established_for_another_name_is_not_learned(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'{"cues":[{"id":"1","text":"弗吉尼亞的英語。"}],"names":{"English":"弗吉尼亞"}}'
    cues,names=backend.translate([Cue('a',0,1,'Virginia English.')],'zh-TW','en',TranslationContext(glossary={'Virginia':'弗吉尼亞'},new_names=('English',)))
    assert names=={}

def test_single_token_names_get_a_pattern_without_the_middle_dot(tmp_path):
    backend=Backend(tmp_path);calls=[]
    def send(prompt,max_tokens,schema=None,system=None):
        calls.append(schema);return '{"cues":[{"id":"1","text":"納什和約翰·納什。"}],"names":{"Nash":"納什","John_Nash":"約翰·納什"}}'
    backend.send=send
    backend.translate([Cue('a',0,1,'Nash and John Nash.')],'zh-TW','en',TranslationContext(new_names=('Nash','John Nash')))
    props=calls[0]['properties']['names']['properties']
    assert props['Nash']['pattern']=='^[㐀-鿿]+$' and props['John_Nash']['pattern']=='^[㐀-鿿·]+$'

def test_a_rendering_owned_anywhere_in_the_ledger_is_not_learned_for_another_name(tmp_path):
    # "John" was learned in an earlier window; it is not among the entries selected for this
    # prompt, but its rendering is still taken.
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'{"cues":[{"id":"1","text":"嘿，約翰·納西。"}],"names":{"Nash":"約翰"}}'
    cues,names=backend.translate([Cue('a',0,1,'Hey, Nash.')],'zh-TW','en',TranslationContext(new_names=('Nash',),taken=frozenset({'約翰'})))
    assert names=={}

def test_translate_reports_which_names_the_model_returned_and_which_were_rejected(tmp_path):
    backend=Backend(tmp_path)
    backend.send=lambda prompt,max_tokens,schema=None,system=None:'{"cues":[{"id":"1","text":"來吧，本德。"}],"names":{"Bender":"班德","Nash":"納什"}}'
    cues,names=backend.translate([Cue('a',0,1,'Come on, Bender. Nash?')],'zh-TW','en',TranslationContext(new_names=('Bender','Nash')))
    assert names=={} and backend.names_report=={'reported':{'Bender':'班德','Nash':'納什'},'accepted':{},'rejected':{'Bender':'班德','Nash':'納什'},'fallback':False}

def test_a_names_request_that_fell_back_is_reported(tmp_path):
    backend=Backend(tmp_path)
    replies=iter(['not json','[{"id":"1","text":"納許來了"}]'])
    backend.send=lambda prompt,max_tokens,schema=None,system=None:next(replies)
    backend.translate([Cue('a',0,1,'Nash came.')],'zh-TW','en',TranslationContext(new_names=('Nash',)))
    assert backend.names_report['fallback'] is True and backend.names_report['reported']=={}

def test_the_prompt_carries_the_ten_most_recent_previous_pairs(tmp_path):
    backend=Backend(tmp_path);prompts=[]
    backend.send=lambda prompt,max_tokens,schema=None,system=None: prompts.append(prompt) or '[{"id":"1","text":"你好"}]'
    previous=tuple((f'line {i}',f'譯{i}') for i in range(12))
    backend.translate([Cue('a',0,1,'Hello.')],'zh-TW','en',TranslationContext(previous=previous))
    assert '"source": "line 2"' in prompts[0] and '"source": "line 11"' in prompts[0] and '"source": "line 1"' not in prompts[0]

class DedicatedAsr:
    key='mlx-asr:test'
    def __init__(self): self.loaded=False; self.calls=[]
    def load(self): self.loaded=True
    def transcribe(self, audio, source='auto', names=(), previous=''): self.calls.append((audio,source,tuple(names),previous)); return 'Hello.'

def test_transcription_delegates_to_a_dedicated_asr_engine_when_one_is_set(tmp_path):
    asr=DedicatedAsr();backend=Backend(tmp_path,asr=asr)
    backend.send=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Gemma must not transcribe'))
    assert backend.transcribe(tmp_path/'a.wav','en',names=['Nash'],previous='Earlier line.')=='Hello.'
    assert asr.calls==[(tmp_path/'a.wav','en',('Nash',),'Earlier line.')]
    with pytest.raises(CueError): backend.transcribe(tmp_path/'a.wav','xx')

def test_loading_the_backend_loads_the_dedicated_asr_engine_too(tmp_path,monkeypatch):
    (tmp_path/'gemma').mkdir(); (tmp_path/'aligner').mkdir()
    (tmp_path/'gemma/gemma-4-E2B-it.litertlm').touch(); (tmp_path/'aligner/model.safetensors').touch()
    engine=SimpleNamespace(close=lambda:None)
    monkeypatch.setitem(sys.modules,'litert_lm',SimpleNamespace(set_min_log_severity=lambda severity:None,LogSeverity=SimpleNamespace(ERROR=1),
        Engine=lambda *args,**kwargs:engine,Backend=SimpleNamespace(GPU=lambda:'gpu',CPU=lambda:'cpu')))
    asr=DedicatedAsr();backend=Backend(tmp_path,asr=asr);backend.load()
    assert asr.loaded is True
    backend.close()

def test_partial_alignment_skips_unplaceable_left_context_words_and_reports_them(tmp_path):
    backend=Backend(tmp_path)
    item=lambda a,b,t:SimpleNamespace(start_time=a,end_time=b,text=t)
    backend.aligner=SimpleNamespace(generate=lambda audio,text,language:SimpleNamespace(items=[item(0,0,'Nash'),item(1.6,1.76,"Who's"),item(1.76,2.08,'winning')]))
    kept,cut,skipped=backend.align(tmp_path/'a.wav',"Nash. Who's winning?",'en',partial=True,left_ms=1000)
    assert [u.text for u in kept]==["Who's",'winning'] and cut is None and [u.text for u in skipped]==['Nash']
    # Without a left context the window still collapses at the unplaceable first word.
    assert backend.align(tmp_path/'a.wav',"Nash. Who's winning?",'en',partial=True)==([],0,[])
