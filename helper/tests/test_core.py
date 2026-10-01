import json
import pytest
from cue.core import Cue, CueError, Settings, SOURCE_LANGUAGES, Unit, assemble, continuous_end, next_window, ranges_merge, srt, stamp, translation_parse, validate_units
from cue.core import coalesce_owned, coalesce_quantized_units, coalesce_until_collapse, restore_transcript, transcript_after
from cue.core import TranslationContext, drop_seam_phantom, hold_back, join_texts, pair_previous, sentence_units

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

def test_sentence_units_merge_fragments_until_a_sentence_ends():
    cues=[Cue('a',0,500,"He's"),Cue('b',600,1500,'going to get her.'),Cue('c',1600,2500,'So then we go'),Cue('d',2500,3200,'for her friends.')]
    units,continues=sentence_units(cues,'zh-TW')
    assert [(u.start_ms,u.end_ms,u.text) for u in units]==[(0,1500,"He's going to get her."),(1600,3200,'So then we go for her friends.')]
    assert continues==frozenset()
    assert units[0].id!=units[1].id and len(units[0].id)==24
    # The id depends on the target, so zh-TW and ja units of the same source never collide in a cache.
    assert sentence_units(cues,'ja')[0][0].id!=units[0].id

def test_sentence_units_split_on_a_long_pause_a_duration_cap_and_width_and_flag_continuations():
    pause=[Cue('a',0,400,'Wait'),Cue('b',4000,4400,'for me.')]
    units,continues=sentence_units(pause,'zh-TW')
    assert [u.text for u in units]==['Wait','for me.'] and continues=={units[1].id}
    long=[Cue(str(i),i*2000,i*2000+1900,'word') for i in range(5)]
    units,continues=sentence_units(long,'zh-TW')
    assert [(u.start_ms,u.end_ms) for u in units]==[(0,5900),(6000,9900)]
    assert continues=={units[1].id}
    wide=[Cue('a',0,1000,'x'*50),Cue('b',1000,2000,'y'*50)]
    assert len(sentence_units(wide,'zh-TW')[0])==2

def test_sentence_units_without_any_punctuation_still_stop_at_seven_seconds():
    cues=[Cue(str(i),i*1000,i*1000+900,f'w{i}') for i in range(10)]
    units,continues=sentence_units(cues,'zh-TW')
    assert [(u.start_ms,u.end_ms) for u in units]==[(0,6900),(7000,9900)]
    assert continues=={units[1].id}

def test_join_texts_keeps_spaces_between_words_but_not_between_cjk():
    assert join_texts(['Hello','world.'])=='Hello world.'
    assert join_texts(['火車','明天'])=='火車明天'
    assert join_texts(['見到 約翰','Nash'])=='見到約翰 Nash'

def test_pair_previous_matches_rendered_cues_to_the_source_cues_inside_their_span():
    source=[Cue('a',0,500,"He's"),Cue('b',600,1500,'going to get her.'),Cue('c',1600,2500,'Later.')]
    rendered=[Cue('u',0,1500,'他會追到她。'),Cue('v',1600,2500,'之後。'),Cue('w',9000,9500,'孤兒')]
    assert pair_previous(source,rendered)==[("He's going to get her.",'他會追到她。'),('Later.','之後。')]

def test_translation_context_defaults_are_empty():
    context=TranslationContext()
    assert context.previous==() and context.glossary=={} and context.variants=={}
    assert context.new_names==() and context.continues==frozenset()

def test_hold_back_leaves_an_unfinished_trailing_sentence_for_the_next_window():
    cues=[Cue('a',500,2500,'Not a single one of us.'),Cue('b',3000,3400,"He's")]
    assert hold_back(cues,0,4000,2000)==([cues[0]],3000)

def test_hold_back_does_nothing_when_the_window_ends_on_a_sentence_or_the_tail_is_too_long():
    assert hold_back([Cue('a',500,2500,'Done.')],0,4000,2000) is None
    tail=[Cue('a',500,2500,'Done.'),Cue('b',3000,9000,'and then he kept talking without a pause')]
    assert hold_back(tail,0,9500,2000) is None
    assert hold_back(tail,0,9500,2000,max_hold_ms=7000)==([tail[0]],3000)
    assert hold_back([],0,4000,2000) is None

def test_hold_back_keeps_the_minimum_committed_stretch():
    cues=[Cue('a',500,1500,'Short.'),Cue('b',1600,3000,"He's")]
    assert hold_back(cues,0,4000,2000) is None
    assert hold_back(cues,0,4000,1000)==([cues[0]],1600)
    # With no sentence end at all, everything from the first cue on is the tail.
    cues=[Cue('a',2500,3000,"He's"),Cue('b',3100,4000,'going')]
    assert hold_back(cues,0,5000,2000)==([],2500)

def test_a_tiny_first_unit_on_the_window_seam_is_dropped():
    units=[Unit(1000,1040,"I'm"),Unit(8800,9200,'Smith'),Unit(9300,9600,'needs')]
    assert drop_seam_phantom(units,1000)==(units[1:],1)
    # The seam is fuzzy by one aligner bin: a unit starting 40 ms before the core start counts too.
    assert drop_seam_phantom([Unit(960,1040,'ね。'),Unit(4000,4400,'そう')],1000)==([Unit(4000,4400,'そう')],1)

def test_longer_or_later_first_units_and_lone_units_are_kept():
    units=[Unit(1000,1400,'Hello'),Unit(1500,1900,'there')]
    assert drop_seam_phantom(units,1000)==(units,0)
    units=[Unit(3000,3080,'Oh'),Unit(6000,6400,'no')]
    assert drop_seam_phantom(units,1000)==(units,0)
    assert drop_seam_phantom([Unit(1000,1040,'year.')],1000)==([Unit(1000,1040,'year.')],0)

def test_the_seam_test_applies_to_the_first_unit_this_window_owns_not_to_left_context_words():
    # Words aligned inside the 1 s left context belong to the previous window; the phantom sits after them.
    context=[Unit(200,600,'history'),Unit(650,990,'book.')]
    units=[*context,Unit(1000,1040,"I'm"),Unit(8800,9200,'Smith')]
    assert drop_seam_phantom(units,1000)==([*context,Unit(8800,9200,'Smith')],1)

def test_a_chain_of_tiny_units_on_the_seam_is_dropped_but_never_more_than_three():
    chain=[Unit(960,1040,'Oh,'),Unit(1040,1080,'that'),Unit(1080,1120,'is'),Unit(1120,1160,'it'),Unit(6000,6400,'Later')]
    kept,dropped=drop_seam_phantom(chain,1000)
    assert dropped==3 and kept==[Unit(1120,1160,'it'),Unit(6000,6400,'Later')]
    # A real word right after the seam stops the chain.
    units=[Unit(1000,1040,"I'm"),Unit(1100,1500,'going'),Unit(1550,1900,'home')]
    assert drop_seam_phantom(units,1000)==(units[1:],1)

def test_a_lowercase_continuation_bridges_a_longer_pause():
    cues=[Cue('a',0,1600,"How will it be when I'm chosen for Wheeler"),Cue('b',3680,4080,'and you are not?')]
    units,continues=sentence_units(cues,'zh-TW')
    assert [u.text for u in units]==["How will it be when I'm chosen for Wheeler and you are not?"] and continues==frozenset()
    # A capitalised start after the same pause is a new sentence.
    assert [u.text for u in sentence_units([Cue('a',0,1600,'Wait'),Cue('b',3680,4080,'Nash is here.')],'zh-TW')[0]]==['Wait','Nash is here.']
    # The lowercase bridge has its own limit, and a finished sentence is never bridged.
    assert [u.text for u in sentence_units([Cue('a',0,1600,'Wait'),Cue('b',5000,5400,'for me.')],'zh-TW')[0]]==['Wait','for me.']
    assert [u.text for u in sentence_units([Cue('a',0,1600,'Wait.'),Cue('b',3680,4080,'for me.')],'zh-TW')[0]]==['Wait.','for me.']

def test_zero_length_endings_at_the_previous_word_merge_into_it_when_the_next_word_is_too_far():
    # "悪くないじゃん。 と、正三郎は思った": the aligner gives じゃん no length at the end of
    # ない, and a pause follows. The ending belongs to the word it sits on.
    units=[Unit(480,880,'悪く'),Unit(880,1040,'ない'),Unit(1040,1040,'じゃん'),Unit(4000,4200,'と'),Unit(4300,5000,'正三郎')]
    kept,cut,reason=coalesce_until_collapse(units)
    assert (cut,reason)==(None,None)
    assert kept==[Unit(480,880,'悪く'),Unit(880,1040,'ない じゃん',('quantized_tokens_coalesced',)),Unit(4000,4200,'と'),Unit(4300,5000,'正三郎')]

def test_split_digits_at_the_previous_word_merge_back_and_a_later_token_still_merges_forward():
    # "はい、450円。え?": 450円 is split into four tokens, three of them left at the end of 4.
    units=[Unit(1440,1920,'4'),Unit(1920,1920,'5'),Unit(1920,1920,'0'),Unit(1920,1920,'円'),Unit(3360,3360,'え'),Unit(3400,3600,'いくら')]
    kept,cut,_=coalesce_until_collapse(units)
    assert cut is None
    assert kept==[Unit(1440,1920,'4 5 0 円',('quantized_tokens_coalesced',)),Unit(3360,3600,'え いくら',('quantized_tokens_coalesced',))]

def test_more_than_three_endings_at_one_word_still_collapse():
    units=[Unit(0,500,'x'),Unit(500,500,'a'),Unit(500,500,'b'),Unit(500,500,'c'),Unit(500,500,'d'),Unit(3000,3200,'y')]
    kept,cut,reason=coalesce_until_collapse(units)
    assert (kept,cut,reason)==([Unit(0,500,'x')],500,'collapsed alignment span')

def test_a_word_stretched_past_one_and_a_half_seconds_takes_no_endings():
    units=[Unit(0,300,'a'),Unit(300,2300,'long'),Unit(2300,2300,'x'),Unit(5000,5200,'b')]
    kept,cut,reason=coalesce_until_collapse(units)
    assert (kept,cut,reason)==([Unit(0,300,'a'),Unit(300,2300,'long')],2300,'collapsed alignment span')


def test_an_unplaceable_word_in_the_left_context_is_skipped_until_the_window_owns_a_word():
    # "Good evening, Nash. Who's winning?": the previous window committed up to "Good";
    # this one re-hears "Nash" in its first second, and the aligner cannot place it.
    units=[Unit(0,0,'Nash'),Unit(1600,1760,"Who's"),Unit(1760,2080,'winning')]
    kept,cut,reason,skipped=coalesce_owned(units,1000)
    assert (kept,cut,reason)==([Unit(1600,1760,"Who's"),Unit(1760,2080,'winning')],None,None)
    assert skipped==[Unit(0,0,'Nash')]

def test_placed_left_context_words_before_such_a_collapse_are_skipped_with_it():
    units=[Unit(560,720,'one'),Unit(720,800,'of'),Unit(1280,1280,'yours'),Unit(1280,1280,'This'),Unit(3500,3800,'is'),Unit(3800,4000,'mine')]
    kept,cut,reason,skipped=coalesce_owned(units,2000)
    assert (kept,cut)==([Unit(3500,3800,'is'),Unit(3800,4000,'mine')],None)
    assert [u.text for u in skipped]==['one','of','yours','This']

def test_a_collapse_after_an_owned_word_still_cuts_and_no_left_context_changes_nothing():
    units=[Unit(1200,1500,'a'),Unit(1600,1600,'b'),Unit(4000,4200,'c')]
    assert coalesce_owned(units,1000)==([Unit(1200,1500,'a')],1600,'collapsed alignment span',[])
    for case in ([Unit(0,0,'Nash'),Unit(1600,1760,"Who's")], units):
        assert coalesce_owned(case,0)==(*coalesce_until_collapse(case),[])

def test_the_transcript_after_skipped_words_keeps_its_punctuation_and_must_match():
    assert transcript_after("Nash. Who's winning?",[Unit(0,0,'Nash')])==" Who's winning?"
    assert transcript_after('一発でガロス粉々になるの。いくらするの?',[Unit(0,0,x) for x in ['一','発','で','ガロス','粉々','に','なる','の']])=='いくらするの?'
    assert transcript_after('Hello world',[Unit(0,0,'Nash')]) is None
    assert transcript_after('Nash',[Unit(0,0,'Nash')])==''

def test_a_caseless_line_after_an_unfinished_one_bridges_the_same_longer_pause():
    # "本当にトニー滝谷 … だった。": the aligner places the sentence end 2.3 s late. Japanese has
    # no lowercase to say "this continues", so an unfinished previous line says it instead.
    cues=[Cue('a',195280,196800,'本当にトニー滝谷'),Cue('b',199120,199200,'だった。')]
    units,continues=sentence_units(cues,'zh-TW')
    assert [(u.start_ms,u.end_ms,u.text) for u in units]==[(195280,199200,'本当にトニー滝谷だった。')] and continues==frozenset()
    # A finished line is never bridged, and longer lines keep the 3 s limit.
    assert len(sentence_units([Cue('a',0,1600,'渡った。'),Cue('b',3000,3500,'激しい戦争の時代を、')],'zh-TW')[0])==2
    assert len(sentence_units([Cue('a',0,1600,'またいるよ'),Cue('b',8000,8400,'ねえ')],'zh-TW')[0])==2

def test_a_short_sentence_tail_rejoins_its_unfinished_line_within_the_unit_cap():
    # "東京から中国に渡っ … た。": the last syllable of 渡った lands 4.6 s late as an 80 ms blip.
    cues=[Cue('a',227600,229360,'東京から中国に渡っ'),Cue('b',234000,234080,'た。')]
    assert [u.text for u in sentence_units(cues,'zh-TW')[0]]==['東京から中国に渡った。']
    # Never past the seven-second unit cap, and English keeps its own rules.
    assert len(sentence_units([Cue('a',0,1600,'渡っ'),Cue('b',7200,7280,'た。')],'zh-TW')[0])==2
    assert len(sentence_units([Cue('a',0,1600,'Wait'),Cue('b',5000,5080,'no.')],'zh-TW')[0])==2
