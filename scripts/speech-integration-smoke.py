"""Real speech/worker/control test. Acks are simulated, NOT native render proof.

Reuses only this project's generated test-video cache to reproduce its exact
88.673 s boundary and the hole before the existing 121.458 s chunk.
"""
from pathlib import Path
import json,os,sqlite3,subprocess,sys,tempfile,time
from cue.bootstrap import call
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cue-speech-integration-') as folder:
    folder=Path(folder);runtime=folder/'runtime';cache=runtime/'cache';cache.mkdir(parents=True)
    source=sqlite3.connect(root/'.runtime/cache/cache.sqlite3');dest=sqlite3.connect(cache/'cache.sqlite3');source.backup(dest);dest.close();source.close()
    env={**os.environ,'CUE_HOME':str(runtime),'CUE_MODELS':str(root/'.runtime/models')}
    boot=subprocess.run([sys.executable,'-m','cue.cli','ensure'],env=env,capture_output=True,text=True,check=True)
    conn=json.loads(boot.stdout);client=call(conn,'/clients',{})['client_id'];latencies=[];events=[]
    def req(path,body=None,method=None):
        t=time.monotonic();r=call(conn,path,body,client,method);latencies.append(time.monotonic()-t);return r
    def prepare(base,epoch,position):
        seen=0;deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            r=req(base+'/snapshot')
            if r['error']:raise RuntimeError(r['error'])
            artifact=r['artifact']
            if artifact and artifact['revision']>seen:
                req(base+'/render-ack',{'revision':artifact['revision'],'sha256':artifact['sha256'],'seek_epoch':epoch,'success':True})
                seen=artifact['revision'];events.append({'position_ms':position,'epoch':epoch,'prepared':r['prepared_ranges'],'metrics':r['metrics']})
            if any(a<=position and b>=min(r['duration_ms'],position+60000) for a,b in r['prepared_ranges']):return r
            time.sleep(.15)
        raise TimeoutError('speech preparation timed out')
    result={'fixture':'project-generated video','ack':'simulated client, not native IINA','status':'failed'}
    try:
        created=req('/sessions',{'request_id':'speech','path':str(root/'benchmarks/fixtures/generated/cue-player-test.mp4'),'position_ms':30000,'settings':{'source':'auto','target':'zh-TW'}})
        base='/sessions/'+created['session_id']
        first=prepare(base,0,30000)
        req(base+'/playback',{'client_seq':1,'seek_epoch':1,'position_ms':80000,'rate':1},'PUT')
        joined=prepare(base,1,80000)
        original=req('/sessions',{'request_id':'original','path':str(root/'benchmarks/fixtures/generated/cue-player-test.mp4'),'position_ms':45000,'settings':{'source':'auto','target':'original'}})
        reused=prepare('/sessions/'+original['session_id'],0,45000)
        assert reused['metrics'].get('source_cache_hit') is True
        result.update(status='pass',first_ranges=first['prepared_ranges'],joined_ranges=joined['prepared_ranges'],original_reuses_source=True)
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        result.update(events=events,api_p95_ms=sorted(latencies)[int((len(latencies)-1)*.95)]*1000,api_max_ms=max(latencies)*1000)
        (root/'benchmarks/results/speech-integration.json').write_text(json.dumps(result,indent=2))
        req('/client',method='DELETE');call(conn,'/shutdown',{})
        print(json.dumps({k:v for k,v in result.items() if k!='events'},indent=2))
