import json
from cue.backend import Backend
from cue.core import Cue

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
