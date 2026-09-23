"""Real FFmpeg + HTTP + spawned worker test, using generated digital silence.

This exercises lifecycle/coverage, NOT model quality or speech performance.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from cue.bootstrap import call
from cue.media import binary

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="cue-integration-") as temp:
    temp=Path(temp)
    video=temp/'silence.mkv'
    subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=black:s=64x64:r=1:d=80','-f','lavfi','-i','anullsrc=r=16000:cl=mono','-t','80','-c:v','libx264','-c:a','pcm_s16le','-y',str(video)],check=True)
    env={**os.environ,'CUE_HOME':str(temp/'runtime')}
    def boot(_):
        result=subprocess.run([sys.executable,'-m','cue.cli','ensure'],env=env,capture_output=True,text=True,check=True)
        return json.loads(result.stdout)
    with ThreadPoolExecutor(max_workers=4) as pool: connections=list(pool.map(boot,range(4)))
    assert len({c['instance_id'] for c in connections})==1
    conn=connections[0]
    client=call(conn,'/clients',{})['client_id']
    try:
        created=call(conn,'/sessions',{'request_id':'silence','path':str(video),'position_ms':0,'settings':{'target':'original'}},client)
        sid=created['session_id'];base='/sessions/'+sid
        deadline=time.monotonic()+20
        latencies=[]
        while time.monotonic()<deadline:
            t=time.monotonic();state=call(conn,base+'/snapshot',client=client);latencies.append(time.monotonic()-t)
            if state['error']:raise RuntimeError(state['error'])
            if state['prepared_ranges']==[[0,74000]]:break
            time.sleep(.1)
        assert state['prepared_ranges']==[[0,74000]],state
        assert state['installed_ranges']==[] and state['artifact']['cue_count']==0
        artifact=state['artifact']
        acknowledged=call(conn,base+'/render-ack',{'revision':artifact['revision'],'sha256':artifact['sha256'],'seek_epoch':0,'success':True},client)
        assert acknowledged['ready']
        call(conn,base+'/playback',{'client_seq':1,'seek_epoch':1,'position_ms':77000,'rate':1},client,method='PUT')
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=call(conn,base+'/snapshot',client=client)
            if state['prepared_ranges']==[[0,74000],[77000,80000]]:break
            time.sleep(.1)
        assert state['prepared_ranges']==[[0,74000],[77000,80000]],state
        assert state['installed_ranges']==[]
        result={'status':'pass','fixture':'generated digital silence; no model inference','concurrent_bootstraps':4,
                'single_instance':True,'high_water_stop_ms':74000,'seek_prepared_ranges':state['prepared_ranges'],
                'prepared_not_installed':True,'api_latency_max_ms':max(latencies)*1000,
                'api_latency_p95_ms':sorted(latencies)[int((len(latencies)-1)*.95)]*1000}
        (root/'benchmarks/results/control-integration.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:
        call(conn,'/client',client=client,method='DELETE')
        call(conn,'/shutdown',{})
