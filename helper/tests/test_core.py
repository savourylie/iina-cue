import json
import pytest
from cue.core import Cue, CueError, Settings, SOURCE_LANGUAGES, Unit, assemble, continuous_end, next_window, ranges_merge, srt, stamp, translation_parse, validate_units
from cue.core import coalesce_quantized_units, coalesce_until_collapse, restore_transcript

def test_simplified_chinese_target_is_valid_and_separate_from_traditional():
    assert Settings(target='zh-CN').target == 'zh-CN'
    assert Settings(target='zh-TW').target == 'zh-TW'

def test_all_pinned_aligner_languages_are_valid_sources():
    assert SOURCE_LANGUAGES == {"zh":"Chinese","yue":"Cantonese","en":"English",
                                "de":"German","es":"Spanish","fr":"French","it":"Italian",
                                "pt":"Portuguese","ru":"Russian","ko":"Korean","ja":"Japanese"}
    for source in SOURCE_LANGUAGES:
        assert Settings(source=source).source == source
    with pytest.raises(CueError,match='INVALID_SETTINGS'):
        Settings(source='el')

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

def test_transcript_punctuation_splits_sentences_at_aligned_word_times():
    words='We work with teammates and colleagues And now we can begin'.split()
    units=[Unit(i*300,i*300+240,word) for i,word in enumerate(words)]
    transcript='We work with teammates and colleagues. And now we can begin.'
    validate_units(units,4000,transcript)
    restored=restore_transcript(units,transcript)
    assert restored is not None
    cues=assemble(restored,0,0,4000,'p',verbatim=True)
    assert [cue.text for cue in cues]==['We work with teammates and colleagues.','And now we can begin.']
    assert [(cue.start_ms,cue.end_ms) for cue in cues]==[(0,1740),(1800,3240)]

def test_sentence_break_keeps_quotes_and_abbreviations_together():
    words=['Dr','Smith','said','Go','Now','we','start']
    units=[Unit(i*350,i*350+260,word) for i,word in enumerate(words)]
    transcript='Dr. Smith said, "Go!" Now we start.'
    restored=restore_transcript(units,transcript)
    assert restored is not None
    cues=assemble(restored,0,0,3000,'p',verbatim=True)
    assert [cue.text for cue in cues]==['Dr. Smith said, "Go!"','Now we start.']
    assert cues[0].end_ms==1310 and cues[1].start_ms==1400

def test_long_speech_uses_aligned_word_boundaries_without_filling_one_cue():
    words='we are making a simple tool that lets people work with their teammates while everyone keeps track of what matters in the project'.split()
    units=[Unit(i*270,i*270+210,word) for i,word in enumerate(words)]
    transcript=' '.join(words)
    restored=restore_transcript(units,transcript)
    assert restored is not None
    cues=assemble(restored,0,0,7000,'p',verbatim=True)
    assert len(cues)>1
    assert all(len(cue.text)<=64 and cue.end_ms-cue.start_ms<=4500 for cue in cues)
    assert ' '.join(cue.text for cue in cues)==transcript
    assert cues[0].end_ms in {unit.end_ms for unit in units}

def test_clause_boundary_and_cjk_width_break_at_measured_units():
    words=['We','have','already','made','a','clear','plan,','then','we','started','the','work']
    units=[Unit(i*320,i*320+260,word) for i,word in enumerate(words)]
    cues=assemble(units,0,0,4500,'p')
    assert [cue.text for cue in cues]==['We have already made a clear plan,','then we started the work']
    han=[Unit(i*100,i*100+80,'字') for i in range(40)]
    cues=assemble(han,0,0,5000,'p')
    assert len(cues)==2 and all(len(cue.text)<=32 for cue in cues)

def test_no_time_is_invented_inside_one_aligner_unit():
    units=[Unit(100,900,'Hello world This works')]
    restored=restore_transcript(units,'Hello world. This works.')
    assert restored is not None
    cues=assemble(restored,0,0,1000,'p',verbatim=True)
    assert [(c.start_ms,c.end_ms,c.text) for c in cues]==[(100,900,'Hello world. This works.')]

def test_length_break_keeps_article_and_preposition_with_next_phrase():
    words='We really wanted to make something useful for the people'.split()
    units=[Unit(i*500,i*500+400,word) for i,word in enumerate(words)]
    cues=assemble(units,0,0,5500,'p')
    assert [cue.text for cue in cues]==['We really wanted to make something useful','for the people']
    assert cues[0].end_ms==3400 and cues[1].start_ms==3500

def test_tiny_sentence_joins_neighbor_without_extending_a_timestamp():
    units=[Unit(0,900,'We'),Unit(950,1800,'planned.'),
           Unit(1850,1930,'I think.'),Unit(1980,3000,'Now'),Unit(3050,3800,'we begin.')]
    cues=assemble(units,0,0,4000,'p')
    assert len(cues)==2
    assert all(cue.end_ms-cue.start_ms>=700 for cue in cues)
    assert cues[0].start_ms==0 and cues[0].end_ms==1930
    assert cues[1].start_ms==1980 and cues[1].end_ms==3800

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


def test_a_collapse_mid_window_keeps_the_units_before_it():
    units=[Unit(0,300,'私'),Unit(300,600,'は')]+[Unit(700,700,x) for x in 'あいうえ']+[Unit(900,1200,'行く')]
    kept,cut,reason=coalesce_until_collapse(units)
    assert kept==[Unit(0,300,'私'),Unit(300,600,'は')] and cut==700 and reason=='collapsed alignment span'

def test_a_collapsed_token_far_from_the_next_word_cuts_before_it():
    kept,cut,_=coalesce_until_collapse([Unit(0,300,'a'),Unit(400,400,'b'),Unit(2100,2400,'c')])
    assert kept==[Unit(0,300,'a')] and cut==400

def test_a_trailing_collapse_also_drops_the_word_stretched_over_it():
    units=[Unit(0,300,'転ん'),Unit(300,500,'だ'),Unit(13040,15200,'だけ'),Unit(15200,15200,'な')]
    kept,cut,reason=coalesce_until_collapse(units)
    assert kept==[Unit(0,300,'転ん'),Unit(300,500,'だ')] and cut==13040 and reason=='collapsed trailing alignment'

def test_without_a_collapse_nothing_is_cut_and_the_strict_rule_is_unchanged():
    units=[Unit(0,100,'go'),Unit(100,100,'to'),Unit(160,400,'town')]
    assert coalesce_until_collapse(units)==(coalesce_quantized_units(units),None,None)
    with pytest.raises(CueError,match='collapsed trailing alignment'):
        coalesce_quantized_units([Unit(0,300,'a'),Unit(2000,2000,'b')])

def test_a_kept_prefix_must_spell_the_start_of_the_transcript():
    units=[Unit(0,100,'Hello'),Unit(100,200,'world')]
    validate_units(units,1000,'Hello, world. More words here',prefix=True)
    with pytest.raises(CueError,match='incomplete text coverage'):
        validate_units(units,1000,'Hello, world. More words here')
    with pytest.raises(CueError):
        validate_units([Unit(0,100,'world')],1000,'Hello, world.',prefix=True)
    with pytest.raises(CueError):
        validate_units([],1000,'Hello',prefix=True)

def test_punctuation_is_restored_on_a_prefix_only():
    units=[Unit(0,100,'Hello'),Unit(100,200,'world')]
    restored=restore_transcript(units,'Hello, world. 「More」 words',prefix=True)
    assert [u.text for u in restored]==['Hello,',' world.']
    assert [(u.start_ms,u.end_ms) for u in restored]==[(0,100),(100,200)]
