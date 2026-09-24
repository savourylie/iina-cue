import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {acceptSnapshot,actionErrorStatus,coverageStrip,remuxFilename,errorStatus,originalLanguageChoice,partialFailureStatus,readyStatus,statusText,originalLanguageLabel,ownedTrack,PlaybackIntent,preparationStatus,targetSubtitleExists} from '../src/control';
test('prepared reply from old epoch or helper never accepted',()=>{
  const reply={session_id:'s',seek_epoch:1,instance_id:'new'};
  assert.equal(acceptSnapshot(reply,'s',1,'new'),true);
  assert.equal(acceptSnapshot(reply,'s',2,'new'),false);
  assert.equal(acceptSnapshot(reply,'s',1,'old'),false);
});
test('track ownership follows exact path and fresh ID',()=>{
  const list=[{id:8,type:'sub',external:true,'external-filename':'/cue/snapshot.srt'},{id:1,type:'sub',external:true,'external-filename':'/user.srt'}];
  assert.equal(ownedTrack(list,'/cue/snapshot.srt')?.id,8);
  assert.equal(ownedTrack(list,'snapshot.srt'),undefined);
});
test('forced and signs tracks are not full subtitles',()=>{
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'eng',forced:true}],'en'),false);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'eng',title:'Signs & songs'}],'en'),false);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'eng'}],'en'),true);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'jpn'}],'ja'),true);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'kor'}],'ko'),true);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'zh-Hans'}],'zh-CN'),true);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'zh-Hant'}],'zh-TW'),true);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'zh-Hant'}],'zh-CN'),false);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'zh-Hans'}],'zh-TW'),false);
  assert.equal(targetSubtitleExists([{id:1,type:'sub',lang:'zh'}],'zh-CN'),false);
});
test('original output label follows detected language and preserves unknown state',()=>{
  assert.equal(originalLanguageLabel('en'),'English (original)');
  assert.equal(originalLanguageLabel('zh'),'Chinese (original)');
  assert.equal(originalLanguageLabel('ja'),'Japanese (original)');
  assert.equal(originalLanguageLabel('ko'),'Korean (original)');
  assert.equal(originalLanguageLabel('el'),'Greek (original)');
  assert.equal(originalLanguageLabel('ca'),'Catalan (original)');
  assert.equal(originalLanguageLabel('pl'),'Polish (original)');
  assert.equal(originalLanguageLabel('es'),'Spanish (original)');
  assert.equal(originalLanguageLabel('yue'),'Cantonese (original)');
  assert.equal(originalLanguageLabel('und'),'Original language');
  const idle={active:false,unclear:false},working={active:true,unclear:false},unclear={active:true,unclear:true};
  assert.deepEqual(originalLanguageChoice('ca','tentative',working),{label:'Catalan (original)',hint:'Spoken language: Catalan, detected from the transcript and not yet verified.'});
  assert.deepEqual(originalLanguageChoice('en','manual',working),{label:'English (original)',hint:''});
  assert.match(originalLanguageChoice('zh','tentative',working).hint,/Cantonese/);
  assert.doesNotMatch(originalLanguageChoice('ja','tentative',working).hint,/Cantonese/);
  assert.deepEqual(originalLanguageChoice(undefined,'unknown',idle),{label:'Original language',hint:''});
  assert.equal(originalLanguageChoice('und','unknown',working).hint,'Detecting the spoken language…');
  assert.match(originalLanguageChoice('und','unknown',unclear).hint,/not detected yet/);
  assert.doesNotMatch(originalLanguageChoice('und','unknown',unclear).label,/detecting/i);
});
test('source selector exposes every pinned Qwen alignment language',()=>{
  const html=readFileSync('plugin/sidebar.html','utf8');
  const source=html.match(/<select id="source"[^>]*>([\s\S]*?)<\/select>/)?.[1] ?? '';
  const codes=[...source.matchAll(/<option value="([^"]+)">/g)].map(match=>match[1]);
  assert.deepEqual(new Set(codes),new Set(['auto','zh','yue','en','de','es','fr','it','pt','ru','ko','ja']));
});
test('stage status names the work and elapsed time without treating skipped audio as coverage',()=>{
  const snapshot={stage:'loading_model',stage_elapsed_s:12,skipped_language_ranges:[] as number[][]};
  assert.deepEqual(preparationStatus(snapshot),{tone:'working',title:'Preparing captions',detail:'Loading the speech model… · 12 s'});
  snapshot.stage='idle';snapshot.skipped_language_ranges=[[0,20000]];
  const unclear=preparationStatus(snapshot);
  assert.equal(unclear.tone,'warning');assert.equal(unclear.title,'Language unclear');assert.equal(unclear.retry,true);
});
test('status copy keeps error codes out of the headline and pause ownership in the detail',()=>{
  const known=errorStatus('LANGUAGE_UNCERTAIN');
  assert.equal(known.tone,'error');assert.equal(known.code,'LANGUAGE_UNCERTAIN');assert.equal(known.retry,true);
  assert.doesNotMatch(statusText(known),/LANGUAGE_UNCERTAIN/);
  const unknown=errorStatus('HELPER_UNAVAILABLE');
  assert.equal(unknown.title,'Captions stopped');assert.equal(unknown.code,'HELPER_UNAVAILABLE');
  assert.doesNotMatch(statusText(unknown),/HELPER_UNAVAILABLE/);
  assert.match(errorStatus('ALIGNMENT_LANGUAGE_UNSUPPORTED','Greek').detail!,/identified as Greek/);
  assert.equal(actionErrorStatus('OUTPUT_EXISTS').tone,'warning');
  assert.equal(readyStatus(48200,false,false).detail,'Loaded in the player for the next 48 s.');
  assert.match(readyStatus(48200,true,true).detail!,/Press play to continue\.$/);
  assert.match(readyStatus(48200,true,false).detail!,/Video remains paused\.$/);
  const partial=partialFailureStatus(30000);
  assert.equal(partial.tone,'warning');assert.match(partial.detail!,/^30 s of captions remain available/);
});
test('user paused playback is not held or resumed',()=>{
  const p=new PlaybackIntent();assert.equal(p.hold(true),false);p.ready();assert.equal(p.holding,false);
});
test('user play bypasses repeated holds until a new seek/session',()=>{
  const p=new PlaybackIntent();assert.equal(p.hold(false),true);p.userPlay();assert.equal(p.hold(false),false);
  p.reset();assert.equal(p.hold(false),true);
});
test('coverage strip shows loaded, prepared-only and holes after the playhead',()=>{
  const c=coverageStrip([[0,30000],[60000,90000]],[[0,20000]],10000,90000);
  assert.deepEqual(c.installed,[[0,10000/90000]]);
  assert.deepEqual(c.prepared,[[10000/90000,20000/90000],[50000/90000,80000/90000]]);
  assert.equal(c.label,'Loaded in the player for the next 10 s; 40 s more prepared in the next 90 s.');
  const hole=coverageStrip([[30000,60000]],[],0,90000);
  assert.deepEqual(hole.installed,[]);
  assert.match(hole.label,/^Nothing loaded at the playhead yet; 30 s more prepared/);
});
test('MKV filename check rejects folders and existing files before writing',()=>{
  const none=()=>false;
  assert.deepEqual(remuxFilename('','movie.cue-remux.mkv','/tmp/',none),{output:'/tmp/movie.cue-remux.mkv'});
  assert.equal(remuxFilename('copy.mp4','x.mkv','/tmp',none).output,'/tmp/copy.mkv');
  assert.match(remuxFilename('../escape','x.mkv','/tmp',none).error!,/plain filename/);
  assert.match(remuxFilename('.hidden','x.mkv','/tmp',none).error!,/plain filename/);
  assert.match(remuxFilename('taken','x.mkv','/tmp',path=>path==='/tmp/taken.mkv').error!,/already exists/);
});
