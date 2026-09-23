import {test} from 'node:test';
import assert from 'node:assert/strict';

test('concurrent player requests share bootstrap and stale helper replies are rejected',async()=>{
  const connection={host:'127.0.0.1',port:12345,token:'a'.repeat(64),protocol_version:1,instance_id:'helper-one'};
  let boots=0,registrations=0,stale=false,background=false;
  (globalThis as any).CUE_BOOTSTRAP_DEFAULT='/project/cue-helper';
  (globalThis as any).iina={preferences:{get:()=>''},file:{exists:()=>true},utils:{exec:async()=>{boots++;return {status:0,stdout:JSON.stringify(connection)};}},http:{
    post:async(url:string,options:any)=>{
      assert.equal(options.headers.Authorization,`Bearer ${connection.token}`);
      if(url.endsWith('/clients')){registrations++;return {data:{instance_id:'helper-one',client_id:'client-one'}};}
      assert.equal(options.headers['X-Cue-Client'],'client-one');
      assert.deepEqual(JSON.parse(options.data.payload),{request_id:'request'});
      return {data:{instance_id:stale?'helper-two':'helper-one',session_id:'session',error:background?{code:'ALIGNMENT_FAILED'}:null}};
    },get:async()=>({data:{instance_id:'helper-one',job_id:'remux-job',state:'error',error:{code:'REMUX_FAILED'}}}),
    delete:async()=>({data:{instance_id:'helper-one'}})
  }};
  const {rpc,disposeClient}=await import('../src/client');
  const results=await Promise.all([rpc('POST','/sessions',{request_id:'request'}),rpc('POST','/sessions',{request_id:'request'})]);
  assert.equal(results.length,2);assert.equal(boots,1);assert.equal(registrations,1);
  background=true;
  const snapshot=await rpc<any>('POST','/sessions',{request_id:'request'});
  assert.equal(snapshot.error.code,'ALIGNMENT_FAILED');
  const failedRemux=await rpc<any>('GET','/remux/remux-job');
  assert.equal(failedRemux.error.code,'REMUX_FAILED');
  stale=true;
  await assert.rejects(rpc('POST','/sessions',{request_id:'request'}),/HELPER_DISCONNECTED/);
  stale=false;
  // Dropping the lease never bricks the plugin: the next call reconnects.
  disposeClient();
  const revived=await rpc<any>('POST','/sessions',{request_id:'request'});
  assert.equal(revived.session_id,'session');assert.equal(boots,2);assert.equal(registrations,2);
});
