import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {buildSync} from 'esbuild';

test('native entry registers polling before a player window exists and survives window close',async()=>{
  const events=new Map<string,()=>void>();let loads=0,available=false,intervals=0,cleared=0;
  const sidebarMessages=new Map<string,(data:any)=>void>();
  const posted:[string,any][]=[];
  const written:[string,string][]=[];
  let mediaPath='55', folderPrompt='', checkedOutput='';
  let releaseFolder: ((path:string)=>void)|undefined;
  const source=buildSync({entryPoints:['plugin/src/main.ts'],bundle:true,write:false,format:'iife',platform:'neutral',define:{CUE_BOOTSTRAP_DEFAULT:'"/fixture/helper"'}}).outputFiles[0].text;
  const menus:{title:string;items:any[]}[]=[];
  const iina={menu:{item:(title:string,action:()=>void)=>({title,action,items:[] as any[],addSubMenuItem(item:any){this.items.push(item);return this;}}),addItem:(item:any)=>{menus.push(item);}},
    event:{on:(name:string,callback:()=>void)=>{events.set(name,callback);return name;}},
    mpv:{getString:(key:string)=>key==='path'?mediaPath:'55',getNumber:()=>0,getFlag:()=>false,set:()=>{},command:()=>{},getNative:()=>[]},
    preferences:{get:(key:string)=>key==='autoEnable'},
    file:{exists:(path:string)=>{checkedOutput=path;return true;},write:(path:string,content:string)=>{written.push([path,content]);}},
    core:{osd:()=>{}},
    utils:{chooseFile:(title:string)=>{folderPrompt=title;return new Promise<string>(resolve=>{releaseFolder=resolve;});},
      prompt:async()=>'',ask:async()=>false},
    sidebar:{loadFile:()=>{if(!available)throw Error('window unavailable');loads++;},onMessage:(name:string,callback:(data:any)=>void)=>{sidebarMessages.set(name,callback);},postMessage:(name:string,data:any)=>{posted.push([name,data]);}}};
  vm.runInNewContext(source,{iina,setInterval:()=>{intervals++;return 1;},setTimeout:()=>1,clearTimeout:()=>{},clearInterval:()=>{cleared++;}});
  assert.deepEqual(menus.slice(0,2).map(item=>item.title),['Open Cue sidebar','Advanced']);
  assert.ok(!menus.some(item=>['Enable AI subtitles for this video','Stop AI subtitles','Play / continue','Retry at current position'].includes(item.title)));
  assert.deepEqual(menus.find(item=>item.title==='Advanced')?.items.map(item=>item.title),[
    'Remux current video (reset timestamps)…','Export generated subtitles…','Save diagnostics',
    'Diagnostics: player and audio track','Diagnostics: 100 subtitle reloads (test media)']);
  menus.find(item=>item.title==='Advanced')!.items.find(item=>item.title==='Save diagnostics')!.action();
  assert.equal(written[0][0],'@data/cue-session-diagnostic.json');
  assert.equal(JSON.parse(written[0][1]).enabled,false);
  assert.equal(loads,0);assert.equal(intervals,1);assert.ok(events.has('mpv.seek'));
  available=true;events.get('iina.window-loaded')!();assert.equal(loads,1);
  events.get('iina.window-loaded')!();assert.equal(loads,1);
  sidebarMessages.get('action')!({action:'diagnostic'});
  assert.equal(written.length,2);
  // Closing the window must not tear down polling, listeners, or the sidebar
  // contract: a reopened video reconnects on demand instead of failing.
  events.get('iina.window-will-close')!();
  assert.equal(cleared,0);assert.equal(intervals,1);assert.ok(events.has('mpv.seek'));assert.ok(events.has('iina.window-loaded'));
  assert.ok(posted.some(([name,data])=>name==='cue-status'&&data.tone==='off'&&data.title==='AI subtitles are off'&&data.enabled===false));
  events.get('iina.window-loaded')!();assert.equal(loads,1);
  // A user switch-off while file-load cleanup is pending must cancel auto-enable.
  events.get('iina.file-loaded')!();
  sidebarMessages.get('action')!({action:'set-enabled',value:false});
  await Promise.resolve();
  assert.ok(!posted.some(([name,data])=>name==='cue-status'&&data.tone==='error'));
  mediaPath='/fixture/movie.mp4';
  sidebarMessages.get('action')!({action:'remux'});
  assert.match(folderPrompt,/Choose a folder/);
  releaseFolder!('/private/tmp');
  await new Promise<void>(resolve=>setImmediate(resolve));
  const draft=[...posted].reverse().find(([name])=>name==='cue-remux-draft')?.[1];
  assert.equal(draft.active,true);
  assert.equal(draft.folder,'/private/tmp');
  assert.equal(draft.suggested,'movie.cue-remux.mkv');
  sidebarMessages.get('action')!({action:'confirm-remux',filename:''});
  assert.equal(checkedOutput,'/private/tmp/movie.cue-remux.mkv');
  sidebarMessages.get('action')!({action:'confirm-remux',filename:'fixed-copy.mp4'});
  assert.equal(checkedOutput,'/private/tmp/fixed-copy.mkv');
  sidebarMessages.get('action')!({action:'confirm-remux',filename:'../bad'});
  assert.equal(checkedOutput,'/private/tmp/fixed-copy.mkv');
  sidebarMessages.get('action')!({action:'cancel-remux'});
  assert.equal([...posted].reverse().find(([name])=>name==='cue-remux-draft')?.[1].active,false);
  const remuxStatus=[...posted].reverse().find(([name])=>name==='cue-remux-status')?.[1];
  assert.equal(remuxStatus.state,'idle');
  assert.equal(remuxStatus.text,'');
});
