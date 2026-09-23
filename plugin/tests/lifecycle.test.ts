import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {buildSync} from 'esbuild';

test('native entry registers polling before a player window exists',()=>{
  const events=new Map<string,()=>void>();let loads=0,available=false,intervals=0;
  const source=buildSync({entryPoints:['plugin/src/main.ts'],bundle:true,write:false,format:'iife',platform:'neutral',define:{CUE_BOOTSTRAP_DEFAULT:'"/fixture/helper"'}}).outputFiles[0].text;
  const iina={menu:{item:(title:string,action:()=>void)=>({title,action}),addItem:()=>{}},
    event:{on:(name:string,callback:()=>void)=>{events.set(name,callback);return name;}},
    sidebar:{loadFile:()=>{if(!available)throw Error('window unavailable');loads++;},onMessage:()=>{}}};
  vm.runInNewContext(source,{iina,setInterval:()=>{intervals++;return 1;},setTimeout:()=>1,clearTimeout:()=>{},clearInterval:()=>{}});
  assert.equal(loads,0);assert.equal(intervals,1);assert.ok(events.has('mpv.seek'));
  available=true;events.get('iina.window-loaded')!();assert.equal(loads,1);
  events.get('iina.window-loaded')!();assert.equal(loads,1);
});
