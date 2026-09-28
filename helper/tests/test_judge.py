import json
import pytest
from cue.core import Cue, CueError
from cue.judge import judge_items, judge_prompt, judge_schema, parse_verdicts, summarize

def test_judge_items_pair_each_caption_with_its_source_and_neighbours():
    source=[Cue('a',0,500,"He's"),Cue('b',600,1500,'going to get her.'),Cue('c',2000,2500,'Really?'),Cue('d',3000,3500,'Yes.'),Cue('e',9000,9500,'Bye.')]
    rendered=[(0,10000,[Cue('u',0,1500,'他會追到她。'),Cue('v',2000,2500,'真的？'),Cue('w',3000,3500,'對。'),Cue('x',7000,7500,'（無來源）')])]
    items=judge_items(source,rendered)
    assert [i['source'] for i in items]==["He's going to get her.",'Really?','Yes.']
    assert items[1]=={'index':1,'start_ms':2000,'end_ms':2500,'source':'Really?','target':'真的？','before':["He's going to get her."],'after':['Yes.']}
    assert items[0]['before']==[] and items[2]['after']==[]

def test_judge_prompt_and_schema_cover_every_item_in_order():
    items=[{'index':0,'start_ms':0,'end_ms':1,'source':'Hi.','target':'嗨。','before':[],'after':['Bye.']},
           {'index':1,'start_ms':2,'end_ms':3,'source':'Bye.','target':'再見。','before':['Hi.'],'after':[]}]
    prompt=judge_prompt(items,'zh-TW','en')
    assert 'Traditional Chinese' in prompt and 'English' in prompt and '"subtitle": "嗨。"' in prompt and '"before": ["Hi."]' in prompt
    schema=judge_schema(['1','2'])
    assert schema['minItems']==schema['maxItems']==2 and schema['prefixItems'][1]['properties']['id']['const']=='2'
    assert schema['prefixItems'][0]['properties']['score']=={'type':'integer','enum':[1,2,3,4,5]}
    assert schema['prefixItems'][0]['required']==['id','score','source_ok','issue']

def test_parse_verdicts_validates_ids_and_fields():
    raw='[{"id":"1","score":4,"source_ok":true,"issue":""},{"id":"2","score":1,"source_ok":false,"issue":"garbled source"}]'
    assert parse_verdicts(raw,['1','2'])==[{'score':4,'source_ok':True,'issue':''},{'score':1,'source_ok':False,'issue':'garbled source'}]
    for bad in ('[{"id":"1","score":4,"source_ok":true,"issue":""}]','[{"id":"1","score":9,"source_ok":true,"issue":""},{"id":"2","score":1,"source_ok":false,"issue":""}]','not json'):
        with pytest.raises(CueError):
            parse_verdicts(bad,['1','2'])

def test_summarize_reports_mean_distribution_source_problems_and_the_worst():
    results=[{'index':i,'start_ms':i*1000,'end_ms':i*1000+500,'source':f's{i}','target':f't{i}','before':[],'after':[],'score':s,'source_ok':ok,'issue':'x' if s<3 else ''}
             for i,(s,ok) in enumerate([(5,True),(4,True),(2,False),(1,False),(3,True)])]
    summary=summarize(results,worst=2)
    assert summary['count']==5 and summary['mean']==3.0 and summary['distribution']=={'1':1,'2':1,'3':1,'4':1,'5':1}
    assert summary['source_not_ok']==2 and summary['mean_where_source_ok']==4.0
    assert [r['score'] for r in summary['worst']]==[1,2]
