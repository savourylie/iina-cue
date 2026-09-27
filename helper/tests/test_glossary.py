import json
import pytest
from cue.glossary import match_name, proper_nouns

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
