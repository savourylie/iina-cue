import {test} from 'node:test';
import assert from 'node:assert/strict';
import {acceptSnapshot,originalLanguageLabel,ownedTrack,PlaybackIntent,targetSubtitleExists} from '../src/control';
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
  assert.equal(originalLanguageLabel('und'),'Original language (detecting…)');
});
test('user paused playback is not held or resumed',()=>{
  const p=new PlaybackIntent();assert.equal(p.hold(true),false);p.ready();assert.equal(p.holding,false);
});
test('user play bypasses repeated holds until a new seek/session',()=>{
  const p=new PlaybackIntent();assert.equal(p.hold(false),true);p.userPlay();assert.equal(p.hold(false),false);
  p.reset();assert.equal(p.hold(false),true);
});
