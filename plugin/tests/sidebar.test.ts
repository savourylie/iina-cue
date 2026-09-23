import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

test('sidebar switch, error, and retry follow Cue status messages', () => {
  const html = readFileSync('plugin/sidebar.html', 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);
  const elements = new Map<string, {checked: boolean; hidden: boolean; open: boolean; value: number | string; textContent: string; dataset: {action?: string; state?: string; tone?: string}; title?: string; listeners: Map<string, (event: any) => void>; addEventListener: (name: string, callback: (event: any) => void) => void; removeAttribute: (name: string) => void; focus: () => void}>();
  function element(id: string) {
    if (!elements.has(id)) {
      const listeners = new Map<string, (event: any) => void>();
      elements.set(id, {checked:false, hidden:false, open:false, value:NaN, textContent:'', dataset:{}, listeners,
        addEventListener(name, callback) {listeners.set(name, callback);},
        removeAttribute(name) {if(name==='value')this.value=NaN;},focus() {}});
    }
    return elements.get(id)!;
  }
  const messages = new Map<string, (data: any) => void>();
  const posted: [string, any][] = [];
  const advancedButtons = ['remux','export','diagnostic','player-diagnostic','reload-diagnostic'].map(action => {
    const button = element(`advanced-${action}`);
    button.dataset.action = action;
    return button;
  });
  vm.runInNewContext(script, {
    document: {getElementById: element, querySelectorAll: () => advancedButtons},
    iina: {onMessage: (name: string, callback: (data: any) => void) => messages.set(name, callback),
      postMessage: (name: string, data: any) => posted.push([name, data])}
  });
  assert.equal(posted[0][0], 'ready');

  messages.get('cue-status')!({tone:'error', title:'Language not detected', detail:'Choose the source language below, then retry.', retry:true, code:'LANGUAGE_UNCERTAIN', enabled:false});
  assert.equal(element('ai-enabled').checked, false);
  assert.equal(element('status').hidden, false);
  assert.equal(element('status').dataset.tone, 'error');
  assert.equal(element('status-title').textContent, 'Language not detected');
  assert.equal(element('status-detail').textContent, 'Choose the source language below, then retry.');
  assert.doesNotMatch(element('status-title').textContent + element('status-detail').textContent, /LANGUAGE_UNCERTAIN/);
  assert.equal(element('retry').hidden, false);
  element('retry').listeners.get('click')!({});
  assert.equal(posted[posted.length-1][0], 'action');
  assert.equal(posted[posted.length-1][1].action, 'retry');

  element('ai-enabled').listeners.get('change')!({target:{checked:false}});
  assert.equal(posted[posted.length-1][1].action, 'set-enabled');
  assert.equal(posted[posted.length-1][1].value, false);
  messages.get('cue-status')!({tone:'off', title:'AI subtitles are off', enabled:false});
  assert.equal(element('ai-enabled').checked, false);
  assert.equal(element('status').hidden, true);
  messages.get('cue-status')!({tone:'working', title:'Starting', detail:'Loading the local subtitle engine…', enabled:true});
  assert.equal(element('ai-enabled').checked, true);
  assert.equal(element('status').hidden, false);
  assert.equal(element('status').dataset.tone, 'working');
  assert.equal(element('retry').hidden, true);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.doesNotMatch(html, /role="alert"/);
  assert.match(html, /<summary>Advanced<\/summary>/);
  advancedButtons[2].listeners.get('click')!({});
  assert.equal(posted[posted.length-1][1].action, 'diagnostic');

  assert.match(html, /<input id="remux-name" type="text"/);
  assert.doesNotMatch(html, /<textarea[^>]*id="remux-name"/);
  messages.get('cue-remux-draft')!({active:true,folder:'/private/tmp',suggested:'movie.cue-remux.mkv'});
  assert.equal(element('remux-form').hidden,false);
  assert.equal(element('remux-name').value,'movie.cue-remux.mkv');
  assert.equal(element('remux-path').textContent,'Save to: /private/tmp/movie.cue-remux.mkv');
  element('remux-name').value='fixed-copy.mp4';
  element('remux-name').listeners.get('input')!({});
  assert.equal(element('remux-path').textContent,'Save to: /private/tmp/fixed-copy.mkv');
  let prevented=false;
  element('remux-form').listeners.get('submit')!({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
  assert.equal(posted[posted.length-1][1].action,'confirm-remux');
  assert.equal(posted[posted.length-1][1].filename,'fixed-copy.mp4');
  element('remux-cancel').listeners.get('click')!({});
  assert.equal(posted[posted.length-1][1].action,'cancel-remux');
  messages.get('cue-remux-draft')!({active:false});
  assert.equal(element('remux-form').hidden,true);

  messages.get('cue-remux-status')!({text:'Copying streams…',state:'running',progressPct:42});
  assert.equal(element('advanced').open, true);
  assert.equal(element('remux-progress').hidden, false);
  assert.equal(element('remux-bar').value, 42);
  assert.equal(element('remux-percent').textContent, '42%');
  messages.get('cue-remux-status')!({text:'Preparing remux…',state:'running',progressPct:null});
  assert.ok(Number.isNaN(element('remux-bar').value));
  assert.equal(element('remux-percent').textContent, '');
  messages.get('cue-remux-status')!({text:'Verifying timestamps and tracks…',state:'running',progressPct:99});
  assert.equal(element('remux-bar').value, 99);
  messages.get('cue-remux-status')!({text:'Remux complete',state:'complete',progressPct:100});
  assert.equal(element('remux-bar').value, 100);
  messages.get('cue-remux-status')!({text:'Remux failed',state:'error'});
  assert.equal(element('remux-bar').hidden, true);
});
