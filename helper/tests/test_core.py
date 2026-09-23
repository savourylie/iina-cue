import json
import pytest
from cue.core import Cue, CueError, Settings, Unit, assemble, continuous_end, next_window, ranges_merge, srt, stamp, translation_parse, validate_units
from cue.core import coalesce_quantized_units

def test_simplified_chinese_target_is_valid_and_separate_from_traditional():
    assert Settings(target='zh-CN').target == 'zh-CN'
    assert Settings(target='zh-TW').target == 'zh-TW'

def test_quantized_zero_tokens_use_measured_group_boundaries():
    units=coalesce_quantized_units([Unit(0,100,'go'),Unit(100,100,'to'),Unit(160,400,'town')])
    assert units==[Unit(0,100,'go'),Unit(100,400,'to town',('quantized_tokens_coalesced',))]
    validate_units(units,500,'go to town')
    with pytest.raises(CueError):coalesce_quantized_units([Unit(100,100,'only')])

def test_coverage_holes_silence_and_eof():
    assert ranges_merge([[600,630],[0,60],[60,90]]) == [[0,90],[600,630]]
    assert continuous_end([[0,60],[600,630]],30) == 60
    assert continuous_end([[0,60],[600,630]],60) == 60
    assert next_window([[0,10000]],0,10000,Settings()) is None
    assert next_window([],9000,10000,Settings()) == (9000,10000)

def test_high_water_and_seek():
    assert next_window([[0,60000]],0,600000,Settings()) is None
    assert next_window([[0,60000]],400000,600000,Settings()) == (400000,410000)
    assert next_window([[0,60000]],0,600000,Settings(),2) == (60000,76000)
    assert next_window([[5000,8000]],0,60000,Settings()) == (0,5000)
    assert next_window([[0,59000]],0,600000,Settings()) == (59000,75000)

@pytest.mark.parametrize('units', [[Unit(-1,2,'a')],[Unit(3,2,'a')],[Unit(0,0,'a')],[Unit(0,float('nan'),'a')],[Unit(0,1100,'a')],[Unit(500,700,'a'),Unit(600,800,'b')]])
def test_bad_alignment(units):
    with pytest.raises(CueError): validate_units(units,1000,'ab')

def test_alignment_text_and_original_timing():
    units=[Unit(0,200,'hello'),Unit(250,500,'world')]
    validate_units(units,1000,'Hello, world!')
    with pytest.raises(CueError): validate_units(units,1000,'Hello, world, again!')
    cues=assemble(units,40000,40000,41000,'profile')
    assert (cues[0].start_ms,cues[0].end_ms)==(40000,40500)

def test_repeated_words_have_distinct_ids():
    cues=assemble([Unit(0,200,'yes'),Unit(1000,1200,'yes')],0,0,2000,'p')
    assert len(cues)==2 and cues[0].id != cues[1].id

@pytest.mark.parametrize('raw', ['[]','not JSON','[{"id":"x","text":"a"},{"id":"x","text":"b"}]','[{"id":"other","text":"a"}]','[{"id":"x","text":""}]','[{"id":"x","text":"a","start":1}]'])
def test_bad_translations(raw):
    with pytest.raises(CueError): translation_parse(raw,[Cue('x',0,100,'hello')])

def test_translation_keeps_stable_ids():
    assert translation_parse('[{"id":"x","text":"你好"}]',[Cue('x',0,100,'hello')]) == {'x':'你好'}

def test_srt_long_duration_and_sanitizer():
    assert stamp(360000001)=='100:00:00,001'
    output=srt([Cue('a',0,900,'<b>你好</b>\x00{\\an8}')])
    assert output=='1\n00:00:00,000 --> 00:00:00,900\n你好\n'
    with pytest.raises(CueError): srt([Cue('a',0,900,'a'),Cue('b',800,1000,'b')])

def test_boundary_reuses_previous_measured_end_and_rejects_large_conflict():
    from cue.core import reconcile_boundary
    previous=[Cue('a',4800,8880,'we made the')]
    following=[Cue('b',8840,13640,'final decision')]
    settled, overlap=reconcile_boundary(following,previous)
    assert overlap == 40
    assert (settled[0].start_ms,settled[0].end_ms,settled[0].text)==(8880,13640,'final decision')
    assert previous[0].end_ms == 8880
    with pytest.raises(CueError): reconcile_boundary([Cue('x',8000,10000,'conflict')],previous)
