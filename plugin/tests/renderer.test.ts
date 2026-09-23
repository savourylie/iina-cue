import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SubtitleRenderer} from '../src/player';
import type {Track} from '../src/types';

test('100 subtitle updates retain one owned track and discover changed IDs',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let list:Track[]=[];let sid='no';let id=1;const commands:string[]=[];
  (globalThis as any).iina={file:{exists:()=>true},mpv:{
    getNative:()=>list,getString:()=>sid,set:(_name:string,value:unknown)=>{sid=String(value);},
    command:(name:string,args:string[])=>{
      commands.push(name);
      if(name==='sub-add'){list.push({id:id++,type:'sub',external:true,'external-filename':args[0]});sid=String(list[0].id);}
      if(name==='sub-reload'){list[0]={...list[0],id:id++};sid=String(list[0].id);}
      if(name==='sub-remove')list=[];
    }
  }};
  const renderer=new SubtitleRenderer();
  for(let revision=1;revision<=100;revision++){
    const promise=renderer.install({path:'/cue/snapshot.srt',revision,sha256:'hash',cue_count:1,complete_movie:false},revision===1,()=>true);
    t.mock.timers.tick(100);await promise;
    assert.equal(list.length,1);assert.equal(sid,String(list[0].id));
  }
  assert.equal(commands.filter(c=>c==='sub-add').length,1);
  assert.equal(commands.filter(c=>c==='sub-reload').length,99);
  renderer.remove();assert.equal(list.length,0);
});

test('stale async subtitle installation is never acknowledged',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});let current=true;
  (globalThis as any).iina={file:{exists:()=>true},mpv:{getNative:()=>[],getString:()=> 'no',command:()=>{current=false;}}};
  const renderer=new SubtitleRenderer();
  const promise=renderer.install({path:'/cue/a.srt',revision:1,sha256:'x',cue_count:1,complete_movie:false},true,()=>current);
  t.mock.timers.tick(100);
  await assert.rejects(promise,/STALE_ACK/);assert.equal(renderer.installed,0);
});
