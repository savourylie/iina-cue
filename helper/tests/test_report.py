from cue.core import Cue
from cue.report import dump_report, fragment_count, name_table, side_by_side
from cue.storage import Cache

def test_side_by_side_pairs_captions_with_their_source_and_marks_uncaptioned_source():
    source=[Cue('a',500,800,"He's"),Cue('b',900,1500,'going to get her.'),Cue('c',3000,3500,'Nash!'),Cue('d',20000,20500,'Late.')]
    rendered=[(0,10000,[Cue('u',500,1500,'他會追到她。')]),(10000,26000,[])]
    assert side_by_side(source,rendered)==[
        '--- window 00:00:00,000-00:00:10,000 ---',
        "[00:00:00,500-00:00:01,500] He's going to get her.",'    => 他會追到她。',
        '[00:00:03,000-00:00:03,500] Nash!','    => (no caption)',
        '--- window 00:00:10,000-00:00:26,000 ---',
        '[00:00:20,000-00:00:20,500] Late.','    => (no caption)']
    assert side_by_side(source,rendered,from_ms=10000)[0]=='--- window 00:00:10,000-00:00:26,000 ---'

def test_name_table_counts_mentions_and_consistent_captions():
    source=[Cue('a',0,1000,'Meet John Nash.'),Cue('b',2000,3000,'Nash is late.'),Cue('c',4000,5000,'Ask Hansen.')]
    rendered=[Cue('u',0,1000,'見到約翰·納許。'),Cue('v',2000,3000,'納什遲到了。'),Cue('w',4000,5000,'問漢森。')]
    rows=name_table(source,rendered,{'Nash':'納許'})
    assert rows[0]=={'name':'Nash','rendering':'納許','mentions':2,'captions':2,'consistent':1,'samples':['見到約翰·納許。','納什遲到了。']}
    assert [r['name'] for r in rows[1:]]==['John Nash','Hansen'] and rows[2]['rendering'] is None and rows[2]['consistent'] is None

def test_fragment_count_flags_captions_with_fewer_than_three_source_words():
    source=[Cue('a',0,500,"He's"),Cue('b',600,1500,'going to get her.'),Cue('c',2000,2500,'book.')]
    assert fragment_count(source,[Cue('u',0,1500,'x'),Cue('v',2000,2500,'y')])==1

def test_dump_report_uses_the_latest_profiles_for_the_media(tmp_path):
    cache=Cache(tmp_path/'cache')
    cache.register('old-src','media','original');cache.register('src','media','original');cache.register('tgt','media','zh-TW')
    cache.put('old-src',0,1000,[Cue('o',0,500,'old')],{'code':'en'})
    cache.put('src',0,1000,[Cue('s',0,500,'Hello Nash.')],{'code':'en'})
    cache.put('tgt',0,1000,[Cue('t',0,500,'哈囉，納許。')],{'code':'en'})
    report=dump_report(cache,'media','zh-TW',{'Nash':'納許'})
    assert '[00:00:00,000-00:00:00,500] Hello Nash.' in report and '    => 哈囉，納許。' in report and 'old' not in report
    assert 'Nash => 納許  mentions 1 consistent 1/1' in report
    assert 'captions with fewer than 3 source words: 1 of 1' in report
    assert dump_report(cache,'media','ja',{})=='no cached captions for this media and target ja'

def test_dump_report_counts_builtin_renderings_as_established(tmp_path):
    cache=Cache(tmp_path/'cache')
    cache.register('src','media','original');cache.register('tgt','media','zh-TW')
    cache.put('src',0,1000,[Cue('s',0,500,'Hello John.')],{'code':'en'})
    cache.put('tgt',0,1000,[Cue('t',0,500,'哈囉，約翰。')],{'code':'en'})
    assert 'John => 約翰  mentions 1 consistent 1/1' in dump_report(cache,'media','zh-TW',{})
