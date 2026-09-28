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

from cue.judge import judge_captions
from cue.storage import Cache

class FakeJudge:
    """Answers a judge prompt per item; raises for any batch that contains a poisoned line."""
    name="fake"
    def __init__(self, poison=None, fail_large=False):
        self.poison=poison; self.fail_large=fail_large; self.calls=[]
    def load(self): pass
    def close(self): pass
    def send(self, prompt, max_tokens=768, schema=None, system=None):
        rows=json.loads(prompt[prompt.index('\n[')+1:])
        self.calls.append(len(rows))
        if self.fail_large and len(rows)>2: raise CueError('JUDGE_FAILED','invalid verdict JSON')
        if self.poison and any(self.poison in r['line'] for r in rows): raise RuntimeError('engine')
        return json.dumps([{'id':r['id'],'score':5 if 'good' in r['line'] else 3,'source_ok':True,'issue':''} for r in rows])

def seeded_cache(tmp_path,lines):
    cache=Cache(tmp_path/'cache');cache.register('src','media','original');cache.register('tgt','media','zh-TW')
    cache.put('src',0,100000,[Cue(f's{i}',i*1000,i*1000+500,line) for i,line in enumerate(lines)],{'code':'en'})
    cache.put('tgt',0,100000,[Cue(f't{i}',i*1000,i*1000+500,f'譯{i}') for i in range(len(lines))],{'code':'en'})
    return cache

def test_a_failing_batch_is_split_and_a_single_bad_item_is_marked_unjudged(tmp_path):
    lines=[f'good line {i}' for i in range(10)]+['bad line']
    fake=FakeJudge(poison='bad',fail_large=True)
    report=judge_captions(seeded_cache(tmp_path,lines),'media','zh-TW',tmp_path/'gemma.litertlm',tmp_path,backend=fake)
    scores=[r['score'] for r in report['results']]
    assert scores[:10]==[5]*10 and scores[10] is None and report['results'][10]['issue']=='unjudged'
    assert max(fake.calls)==8 and 1 in fake.calls
    assert report['summary']['count']==11 and report['summary']['unjudged']==1 and report['summary']['mean']==5.0

def test_summary_counts_sources_the_judge_suspects_in_its_wording_too():
    results=[{'index':0,'start_ms':0,'end_ms':1,'source':'a','target':'b','before':[],'after':[],'score':1,'source_ok':False,'issue':''},
             {'index':1,'start_ms':2,'end_ms':3,'source':'a','target':'b','before':[],'after':[],'score':1,'source_ok':True,'issue':"'gas mark' is likely a mishearing of something else"},
             {'index':2,'start_ms':4,'end_ms':5,'source':'a','target':'b','before':[],'after':[],'score':2,'source_ok':True,'issue':'The transcription looks garbled'},
             {'index':3,'start_ms':6,'end_ms':7,'source':'a','target':'b','before':[],'after':[],'score':5,'source_ok':True,'issue':''}]
    summary=summarize(results)
    assert summary['source_not_ok']==1 and summary['source_suspect']==3 and summary['mean_where_source_clean']==5.0

import urllib.error
import cue.judge
from cue.judge import RemoteJudge, load_dotenv, remote_judge_from_env

class FakeResponse:
    def __init__(self, body): self.body=body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self,*a): return False

def test_remote_judge_posts_an_openai_style_chat_request_and_returns_the_json_array(monkeypatch):
    captured={}
    def fake_urlopen(req, timeout=0):
        captured['url']=req.full_url; captured['auth']=req.get_header('Authorization'); captured['body']=json.loads(req.data); captured['timeout']=timeout
        captured['agent']=req.get_header('User-agent'); captured['session']=req.get_header('X-opencode-session'); captured['accept']=req.get_header('Accept')
        return FakeResponse(json.dumps({"choices":[{"message":{"content":"```json\n[{\"id\":\"1\",\"score\":5,\"source_ok\":true,\"issue\":\"\"}]\n```"}}]}).encode())
    monkeypatch.setattr(cue.judge.urllib.request,'urlopen',fake_urlopen)
    judge=RemoteJudge('https://example.test/v1/chat/completions','deepseek-v4-flash','sk-test')
    raw=judge.send('grade this',max_tokens=512,schema={'type':'array'})
    assert raw=='[{"id":"1","score":5,"source_ok":true,"issue":""}]'
    assert captured['url']=='https://example.test/v1/chat/completions' and captured['auth']=='Bearer sk-test' and captured['timeout']==300
    # The gateway sits behind Cloudflare (a bare urllib agent gets 403) and routes on a session id; the
    # model reasons before answering, so the budget is raised and reasoning kept short.
    assert captured['agent'].startswith('cue-judge/') and captured['accept']=='application/json' and len(captured['session'])>=8
    assert captured['body']['model']=='deepseek-v4-flash' and captured['body']['temperature']==0 and captured['body']['max_tokens']==8000
    assert captured['body']['reasoning_effort']=='low' and captured['body']['messages']==[{'role':'user','content':'grade this'}]
    assert 'sk-test' not in repr(judge) and judge.name=='deepseek-v4-flash'
    assert RemoteJudge('u','m','k').session!=judge.session

def test_an_empty_answer_from_a_reasoning_model_is_a_judge_failure(monkeypatch):
    monkeypatch.setattr(cue.judge.urllib.request,'urlopen',lambda req,timeout=0:FakeResponse(b'{"choices":[{"finish_reason":"length","message":{"content":"","reasoning_content":"still thinking [1]"}}]}'))
    with pytest.raises(CueError) as exc:
        RemoteJudge('https://x','m','k').send('p')
    assert exc.value.code=='JUDGE_FAILED'

def test_remote_judge_failures_are_judge_failures(monkeypatch):
    def down(req, timeout=0): raise urllib.error.URLError('down')
    monkeypatch.setattr(cue.judge.urllib.request,'urlopen',down)
    with pytest.raises(CueError) as first:
        RemoteJudge('https://x','m','k').send('p')
    monkeypatch.setattr(cue.judge.urllib.request,'urlopen',lambda req,timeout=0:FakeResponse(b'{"choices":[{"message":{"content":"no array here"}}]}'))
    with pytest.raises(CueError) as second:
        RemoteJudge('https://x','m','k').send('p')
    assert first.value.code==second.value.code=='JUDGE_FAILED'

def test_dotenv_fills_only_unset_variables_and_the_remote_judge_needs_all_three(tmp_path,monkeypatch):
    for k in ('OPENCODE_GO_URL','OPENCODE_GO_MODEL','OPENCODE_GO_API_KEY'): monkeypatch.delenv(k,raising=False)
    with pytest.raises(CueError) as missing:
        remote_judge_from_env()
    assert missing.value.code=='SETUP_REQUIRED'
    env=tmp_path/'.env';env.write_text('# comment\nOPENCODE_GO_URL=https://x/v1/chat/completions\nOPENCODE_GO_MODEL=m\nOPENCODE_GO_API_KEY="k"\n',encoding='utf-8')
    monkeypatch.setenv('OPENCODE_GO_MODEL','already')
    load_dotenv(env)
    judge=remote_judge_from_env()
    assert judge.name=='already' and judge.url=='https://x/v1/chat/completions'
    load_dotenv(tmp_path/'missing.env')

def test_judge_captions_can_rejudge_the_items_of_an_earlier_report(tmp_path):
    items=[{'index':0,'start_ms':0,'end_ms':500,'source':'good line','target':'譯0','before':[],'after':[]}]
    fake=FakeJudge()
    report=judge_captions(None,'media','zh-TW',None,tmp_path,backend=fake,items=items,language='en')
    assert report['results'][0]['score']==5 and report['judge']=='fake' and report['language']=='en'
