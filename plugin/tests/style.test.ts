import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SubtitleSize,SubtitleStyle,validSubtitleSize} from '../src/style';

function fakeMpv() {
  const values = new Map([
    ['options/sub-color', '#FFEFEFEF'],
    ['options/sub-back-color', '#44000000'],
    ['options/sub-border-size', '3'],
    ['options/sub-shadow-offset', '0'],
    ['options/sub-font-size', '55'],
  ]);
  return {values, getString(name: string) {return values.get(name) || '';},
    set(name: string, value: string) {values.set(name, value);}};
}

test('black box mode uses white text and semitransparent background, then restores player style',()=>{
  const mpv=fakeMpv(); const before=new Map(mpv.values); const style=new SubtitleStyle(mpv);
  style.enable();
  assert.equal(mpv.getString('options/sub-color'),'#FFFFFFFF');
  assert.equal(mpv.getString('options/sub-back-color'),'#99000000');
  assert.equal(mpv.getString('options/sub-border-size'),'0');
  style.restore();
  assert.deepEqual(mpv.values,before);
});

test('restoring Cue style preserves a user change made while Cue was active',()=>{
  const mpv=fakeMpv(); const style=new SubtitleStyle(mpv);
  style.enable(); mpv.set('options/sub-color','#FF00FF00'); style.restore();
  assert.equal(mpv.getString('options/sub-color'),'#FF00FF00');
  assert.equal(mpv.getString('options/sub-border-size'),'3');
});

test('subtitle size changes live and restores the original player value',()=>{
  const mpv=fakeMpv(); const size=new SubtitleSize(mpv);
  assert.equal(size.current(),55);
  size.apply(42); assert.equal(mpv.getString('options/sub-font-size'),'42');
  size.apply(68); assert.equal(mpv.getString('options/sub-font-size'),'68');
  size.restore(); assert.equal(mpv.getString('options/sub-font-size'),'55');
  assert.equal(validSubtitleSize(10),undefined);
  assert.equal(validSubtitleSize(60.5),undefined);
});

test('stopping Cue does not overwrite a later player subtitle-size change',()=>{
  const mpv=fakeMpv(); const size=new SubtitleSize(mpv);
  size.apply(42); mpv.set('options/sub-font-size','72'); size.restore();
  assert.equal(mpv.getString('options/sub-font-size'),'72');
});
