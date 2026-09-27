import json
import pytest
from cue.glossary import glossary_hash, load_user_glossary, match_name, names_hint, proper_nouns, select_entries

def test_proper_nouns_find_names_and_phrases_but_not_sentence_starts_or_stopwords():
    texts=["Hansen won the Carnegie scholarship.","Well, he has his sights set on Wheeler Labs.","Nash. Oh, Mr. Sol is here."]
    new,variants=proper_nouns(texts,["Then Hansen said no."],{},'en')
    assert new==['Hansen','Carnegie','Wheeler Labs','Sol']
    assert variants=={}

def test_a_capitalised_sentence_start_counts_once_it_is_seen_mid_sentence():
    assert proper_nouns(["Nash is late."],[],{},'en')==([],{})
    assert proper_nouns(["Nash is late."],["I saw Nash yesterday."],{},'en')==(['Nash'],{})
    assert proper_nouns(["Meet John Nash.","Nash is late."],[],{},'en')==(['John Nash','Nash'],{})

def test_misheard_spellings_map_to_the_established_name_and_short_names_match_exactly():
    known={'Hansen':'漢森','Sol':'索爾','Nash':'納許'}
    new,variants=proper_nouns(["Thank you, Mr. Hanson.","Hi, Hans.","There goes Saw."],[],known,'en')
    assert new==['Saw'] and variants=={'Hanson':'Hansen','Hans':'Hansen'}
    assert match_name('Nash',known)=='Nash' and match_name('Nasch',known)=='Nash'
    assert match_name('Sal',known) is None and match_name('Bender',known) is None

def test_possessives_all_caps_shouting_and_non_latin_sources():
    assert proper_nouns(["That is Hansen's problem."],[],{},'en')==(['Hansen'],{})
    assert proper_nouns(["STOP IT NOW."],[],{},'en')==([],{})
    assert proper_nouns(["She works at MIT now."],[],{},'en')==(['MIT'],{})
    assert proper_nouns(["ナッシュ さん"],[],{},'ja')==([],{})

def test_at_most_six_new_names_per_batch_in_order_of_appearance():
    text="I met Alpha, Bravo, Charlie, Delta, Echo, Foxtrot and Golf."
    assert proper_nouns([text],[],{},'en')[0]==['Alpha','Bravo','Charlie','Delta','Echo','Foxtrot']
    assert len(proper_nouns([text],[],{},'en',limit=None)[0])==7

def test_select_entries_prefers_relevant_then_recent_and_keeps_user_entries_first():
    user={'Nash':'納許','Morse':'摩斯'}
    learned=[[f'Name{i}',f'名{i}',i*1000] for i in range(50,0,-1)]+[['Hansen','漢森',100],['Governing dynamics','支配動力學',200]]
    chosen=select_entries(user,learned,["Mr. Hanson, governing dynamics is Nash's idea."],[])
    keys=list(chosen)
    assert keys[0]=='Nash' and 'Hansen' in chosen and 'Governing dynamics' in chosen and 'Morse' not in chosen
    assert keys[-10:]==[f'Name{i}' for i in range(50,40,-1)]
    assert len(chosen)==13

def test_select_entries_caps_at_forty():
    learned=[[f'N{i}',f'名{i}',i] for i in range(100)]
    chosen=select_entries({},learned,[" ".join(f'N{i}' for i in range(100))],[])
    assert len(chosen)==40 and list(chosen)[0]=='N0'

def test_names_hint_puts_user_entries_first_and_stops_at_twenty():
    learned=[[f'L{i}','x',i] for i in range(30)]+[['Nash','納什',0]]
    hint=names_hint({'Nash':'納許'},learned)
    assert hint[0]=='Nash' and len(hint)==20 and hint.count('Nash')==1 and hint[1]=='L0'

def test_user_files_merge_with_the_sidecar_winning_and_bad_files_are_ignored(tmp_path):
    root=tmp_path/'runtime';root.mkdir()
    video=tmp_path/'A Beautiful Mind (2001).mp4';video.touch()
    sidecar=tmp_path/'A Beautiful Mind (2001).cue-glossary.json'
    (root/'glossary.json').write_text(json.dumps({'zh-TW':{'Nash':'納什','Morse':'摩斯'},'ja':{'Nash':'ナッシュ'}}),encoding='utf-8')
    sidecar.write_text(json.dumps({'zh-TW':{'Nash':'納許'}}),encoding='utf-8')
    assert load_user_glossary(str(video),root,'zh-TW')=={'Nash':'納許','Morse':'摩斯'}
    assert load_user_glossary(str(video),root,'ja')=={'Nash':'ナッシュ'}
    assert load_user_glossary(str(video),root,'ko')=={}
    events=[]
    sidecar.write_text('{not json',encoding='utf-8')
    assert load_user_glossary(str(video),root,'zh-TW',log=events.append)=={'Nash':'納什','Morse':'摩斯'}
    assert events==['sidecar']
    sidecar.unlink();sidecar.symlink_to(root/'glossary.json')
    assert load_user_glossary(str(video),root,'zh-TW',log=events.append)=={'Nash':'納什','Morse':'摩斯'}
    assert events==['sidecar','sidecar']

def test_user_entries_are_validated(tmp_path):
    root=tmp_path/'runtime';root.mkdir();video=tmp_path/'film.mp4';video.touch()
    events=[]
    bad=[{'zh-TW':{'Nash':['納許']}},{'zh-TW':{'Nash':''}},{'zh-TW':{'Nash':'ナッシュ'}},{'zh-TW':{'':'x'}},{'zh-TW':{'Nash':'x'*65}},['list']]
    for entry in bad:
        (root/'glossary.json').write_text(json.dumps(entry),encoding='utf-8')
        assert load_user_glossary(str(video),root,'zh-TW',log=events.append)=={}
    assert events==['global']*len(bad)
    (root/'glossary.json').write_text(json.dumps({'ja':{'Nash':'ナッシュ'},'ko':{'Nash':'내시'}}),encoding='utf-8')
    assert load_user_glossary(str(video),root,'ja',log=events.append)=={'Nash':'ナッシュ'}
    assert load_user_glossary(str(video),root,'ko',log=events.append)=={'Nash':'내시'}
    (root/'glossary.json').write_text('x'*(256*1024+1),encoding='utf-8')
    assert load_user_glossary(str(video),root,'zh-TW',log=events.append)=={}
    assert events[-1]=='global'
    assert glossary_hash({})=='none'
    assert glossary_hash({'a':'b'})==glossary_hash({'a':'b'})!=glossary_hash({'a':'c'})

def test_accented_names_in_other_latin_sources_are_whole_tokens():
    assert proper_nouns(["Hola, José y André están aquí.","Chloé est là."],[],{},'es')==(['José','André'],{})
    assert match_name('Andre',{'André':'安德烈'})=='André'

def test_hyphenated_and_inner_apostrophe_names_stay_whole():
    assert proper_nouns(["I met Jean-Luc there."],[],{},'en')==(['Jean-Luc'],{})
    assert proper_nouns(["Ask McCoy about O'Brien."],[],{},'en')==(['McCoy'],{})

def test_a_capitalised_word_after_an_opening_quote_dash_or_ellipsis_opens_a_sentence():
    assert proper_nouns(['"Meet me at five."','- Meet me at five.','Well… Meet me later.','Wait... Meet me.'],[],{},'en')==([],{})
    assert proper_nouns(['"Nash, meet me at five."'],['I saw Nash.'],{},'en')==(['Nash'],{})

def test_a_trailing_apostrophe_is_not_part_of_a_name():
    assert proper_nouns(["Take Peros' car and Hansen's hat."],[],{},'en')==(['Peros','Hansen'],{})
