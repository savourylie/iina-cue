import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {setupView} from '../src/setup-view';

test('sidebar switch, error, and retry follow Cue status messages', () => {
  const html = readFileSync('plugin/sidebar.html', 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);
  const elements = new Map<string, {checked: boolean; hidden: boolean; open: boolean; value: number | string; textContent: string; dataset: {action?: string; state?: string; tone?: string}; title?: string; disabled?: boolean; attrs: Map<string, string>; setAttribute: (name: string, value: string) => void; querySelector: (selector: string) => any; replaceChildren: (...nodes: any[]) => void; children: any[]; listeners: Map<string, (event: any) => void>; addEventListener: (name: string, callback: (event: any) => void) => void; removeAttribute: (name: string) => void; focus: () => void}>();
  function element(id: string) {
    if (!elements.has(id)) {
      const listeners = new Map<string, (event: any) => void>();
      const attrs = new Map<string, string>();
      elements.set(id, {checked:false, hidden:false, open:false, value:NaN, textContent:'', dataset:{}, attrs, children:[], listeners,
        setAttribute(name, value) {attrs.set(name, value);}, querySelector(selector) {return element(`${id} ${selector}`);},
        replaceChildren(...nodes) {this.children = nodes;},
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
  const timers: (() => void)[] = [];
  vm.runInNewContext(script, {
    setTimeout: (fn: () => void) => {timers.push(fn); return timers.length;}, clearTimeout: () => {},
    document: {getElementById: element, querySelectorAll: () => advancedButtons, querySelector: (selector: string) => element(selector),
      createElement: () => ({className:'', style:{}})},
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
  assert.equal(element('status-code').textContent, 'Error code: LANGUAGE_UNCERTAIN');
  assert.equal(element('retry').hidden, false);
  assert.equal(element('status-announce').textContent, 'Language not detected. Choose the source language below, then retry.');
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
  assert.equal(element('status-announce').textContent, 'Starting');
  assert.equal(element('status-code').textContent, '');
  messages.get('cue-status')!({tone:'ready', title:'Captions ready', detail:'Loaded in the player for the next 48 s.', enabled:true,
    coverage:{windowMs:90000, installed:[[0,0.5]], prepared:[[0.6,0.8]], label:'Loaded in the player for the next 45 s; 18 s more prepared in the next 90 s.'}});
  assert.equal(element('status-announce').textContent, 'Captions ready');
  assert.equal(element('status-coverage').hidden, false);
  assert.match(element('status-coverage').attrs.get('aria-label')!, /Loaded in the player/);
  assert.equal(element('status-coverage .coverage-track').children.length, 2);
  messages.get('cue-status')!({tone:'info', title:'Subtitles exported', detail:'/tmp/a.srt', reveal:true, enabled:true});
  assert.equal(element('status-coverage').hidden, true);
  assert.equal(element('status-reveal').hidden, false);
  element('status-reveal').listeners.get('click')!({});
  assert.equal(posted[posted.length-1][1].action, 'reveal-export');
  assert.match(html, /role="status" aria-live="polite"/);
  assert.doesNotMatch(html, /role="alert"/);
  assert.match(html, /<summary[^>]*>Advanced<\/summary>/);
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
  timers.pop()!();
  assert.equal(posted[posted.length-1][1].action,'check-remux-name');
  assert.equal(posted[posted.length-1][1].filename,'fixed-copy.mp4');
  messages.get('cue-remux-draft')!({active:true,folder:'/private/tmp',suggested:'movie.cue-remux.mkv',error:'A file with this name already exists.'});
  assert.equal(element('remux-name').value,'fixed-copy.mp4');
  assert.equal(element('remux-error').hidden,false);
  assert.equal(element('remux-name').attrs.get('aria-invalid'),'true');
  assert.equal(element('#remux-form button[type="submit"]').disabled,true);
  messages.get('cue-remux-draft')!({active:true,folder:'/private/tmp',suggested:'movie.cue-remux.mkv',error:''});
  assert.equal(element('remux-error').hidden,true);
  assert.equal(element('#remux-form button[type="submit"]').disabled,false);
  assert.equal(element('remux-path').textContent,'Save to: /private/tmp/fixed-copy.mkv');
  let prevented=false;
  element('remux-form').listeners.get('submit')!({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
  assert.equal(posted[posted.length-1][1].action,'confirm-remux');
  assert.equal(posted[posted.length-1][1].filename,'fixed-copy.mp4');
  element('remux-cancel').listeners.get('click')!({});
  assert.equal(posted[posted.length-1][1].action,'cancel-remux');
  posted.length=0;
  element('remux-name').listeners.get('keydown')!({key:'a',preventDefault(){}});
  assert.equal(posted.length,0);
  element('remux-name').listeners.get('keydown')!({key:'Escape',preventDefault(){}});
  assert.equal(posted[0][1].action,'cancel-remux');
  messages.get('cue-remux-draft')!({active:false});
  assert.equal(element('remux-form').hidden,true);

  messages.get('cue-remux-status')!({text:'Copying streams…',state:'running',progressPct:42,cancellable:true});
  assert.equal(element('remux-stop').hidden, false);
  element('remux-stop').listeners.get('click')!({});
  assert.equal(posted[posted.length-1][1].action, 'stop-remux');
  assert.equal(element('advanced').open, true);
  assert.equal(element('remux-progress').hidden, false);
  assert.equal(element('remux-bar').value, 42);
  assert.equal(element('remux-percent').textContent, '42%');
  messages.get('cue-remux-status')!({text:'Preparing remux…',state:'running',progressPct:null});
  assert.ok(Number.isNaN(element('remux-bar').value));
  assert.equal(element('remux-percent').textContent, '');
  messages.get('cue-remux-status')!({text:'Verifying timestamps and tracks…',state:'running',progressPct:99});
  assert.equal(element('remux-stop').hidden, true);
  assert.equal(element('remux-bar').value, 99);
  messages.get('cue-remux-status')!({text:'Remux complete',state:'complete',progressPct:100});
  assert.equal(element('remux-bar').value, 100);
  assert.equal(element('remux-reveal').hidden, false);
  element('remux-reveal').listeners.get('click')!({});
  assert.equal(posted[posted.length-1][1].action, 'reveal-remux');
  messages.get('cue-remux-status')!({text:'Remux failed',state:'error'});
  assert.equal(element('remux-bar').hidden, true);
  assert.equal(element('remux-reveal').hidden, true);
  messages.get('cue-remux-status')!({text:'MKV copy cancelled.',state:'cancelled'});
  assert.equal(element('remux-stop').hidden, true);
  assert.equal(element('remux-bar').hidden, true);
});

test('first-run setup replaces the normal controls until the smoke test has passed', () => {
  const html = readFileSync('plugin/sidebar.html', 'utf8');
  const preferences = readFileSync('plugin/preferences.html', 'utf8');
  const card = html.slice(html.indexOf('id="setup-card"'), html.indexOf('id="normal-controls"'));
  assert.doesNotMatch(card, /aria-live/);
  assert.equal([...html.matchAll(/aria-live="polite"/g)].length, 2);
  assert.match(card, /<progress id="setup-progress"/);
  assert.match(html, /data-link="gemma"[^>]*>Gemma 4 E2B \(Google, Apache 2.0\)</);
  assert.match(html, /data-link="aligner"[^>]*>Qwen3-ForcedAligner \(Qwen team, Apache 2.0; MLX conversion by mlx-community\)</);
  // Links open model pages through the plugin; none points into the plugin folder or this Mac.
  for (const [, href] of html.matchAll(/<a [^>]*href="([^"]*)"/g)) assert.equal(href, '#');
  // The plugin pack has no licenses folder; the preferences credits name the models without a local link.
  for (const [, href] of preferences.matchAll(/<a [^>]*href="([^"]*)"/g)) assert.match(href, /^https:\/\//);
  assert.match(preferences, /Gemma 4 E2B and the optional E4B \(Google, Apache 2\.0\)/);
  assert.match(preferences, /id="dev-setup" hidden/);
  assert.ok(preferences.indexOf('scripts/setup-dev') > preferences.indexOf('id="dev-setup" hidden'));
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);
  const elements = new Map<string, any>();
  function element(id: string) {
    if (!elements.has(id)) elements.set(id, {hidden: id === 'setup-card', textContent: '', value: 0, dataset: {}, listeners: new Map(), addEventListener(name: string, fn: any) {this.listeners.set(name, fn);}});
    return elements.get(id);
  }
  const messages = new Map<string, (data: any) => void>();
  const posted: [string, any][] = [];
  vm.runInNewContext(script, {
    setTimeout: () => 0, clearTimeout: () => {},
    document: {getElementById: element, querySelectorAll: () => [], querySelector: (selector: string) => element(selector), createElement: () => ({className: '', style: {}})},
    iina: {onMessage: (name: string, fn: any) => messages.set(name, fn), postMessage: (name: string, data: any) => posted.push([name, data])},
  });
  const show = (phase: Parameters<typeof setupView>[0]['phase'], extra: Partial<Parameters<typeof setupView>[0]> = {}) => {
    const view = setupView({phase, ...extra});
    messages.get('cue-setup')!(view);
    return view;
  };
  const download = show('download');
  assert.equal(element('setup-card').hidden, false);
  assert.equal(element('normal-controls').hidden, true);
  assert.equal(download.ready, false);
  assert.equal(posted.some(item => item[0] === 'start-setup'), false);
  element('setup-primary').listeners.get('click')();
  assert.equal(posted[posted.length - 1][0], 'start-setup');
  for (const phase of ['unsupported', 'runtime', 'models', 'verifying', 'smoke', 'failed'] as const) {
    const view = show(phase, {reason: 'macOS 27.0 or later is required.', bytesDone: 40, bytesTotal: 100, previous: phase});
    assert.equal(view.showCard, true);
    assert.equal(view.ready, false);
    assert.equal(view.announce, null);
  }
  const models = show('models', {bytesDone: 40, bytesTotal: 100, previous: 'runtime'});
  assert.equal(models.progress, 40);
  assert.equal(element('setup-progress').value, 40);
  assert.equal(element('setup-bytes').textContent, '0 MB of 0 MB (40%)');
  const large = show('runtime', {bytesDone: 134_000_000, bytesTotal: 267_837_724, previous: 'download'});
  assert.equal(large.bytes, '134 MB of 268 MB (50%)');
  assert.equal(large.detail, 'Step 1 of 3: downloading the helper');
  const done = show('done');
  assert.equal(done.ready, true);
  assert.equal(element('setup-card').hidden, true);
  assert.equal(element('normal-controls').hidden, false);
});

test('an offered update keeps captions usable and names its size; a running one replaces the controls', () => {
  const script = readFileSync('plugin/sidebar.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);
  const elements = new Map<string, any>();
  const element = (id: string) => {
    if (!elements.has(id)) elements.set(id, {hidden: id === 'setup-card', textContent: '', value: 0, dataset: {}, listeners: new Map(), addEventListener(name: string, fn: any) {this.listeners.set(name, fn);}});
    return elements.get(id);
  };
  const messages = new Map<string, (data: any) => void>();
  const posted: [string, any][] = [];
  vm.runInNewContext(script, {
    setTimeout: () => 0, clearTimeout: () => {},
    document: {getElementById: element, querySelectorAll: () => [], querySelector: (selector: string) => element(selector), createElement: () => ({className: '', style: {}})},
    iina: {onMessage: (name: string, fn: any) => messages.set(name, fn), postMessage: (name: string, data: any) => posted.push([name, data])},
  });
  const show = (phase: Parameters<typeof setupView>[0]['phase'], extra: Partial<Parameters<typeof setupView>[0]> = {}) => {
    const view = setupView({phase, mode: 'update', updateBytes: 283_954_324, ...extra});
    messages.get('cue-setup')!(view);
    return view;
  };
  const offer = show('update');
  assert.equal(element('setup-card').hidden, false);
  assert.equal(element('normal-controls').hidden, false, 'the installed helper still works until the user updates');
  assert.equal(element('setup-title').textContent, "Update Cue's helper");
  assert.match(element('setup-intro').textContent, /speech models and subtitles stay/);
  assert.equal(element('setup-credits').hidden, true);
  assert.equal(offer.primary, 'Update');
  assert.equal(offer.detail, 'It is a 284 MB download. Turn off AI subtitles in every IINA window before you update.');
  assert.equal(posted.some(([name]) => name === 'start-setup'), false, 'nothing starts without the button');
  element('setup-primary').listeners.get('click')();
  assert.equal(posted[posted.length - 1][0], 'start-setup');
  const running = show('runtime', {bytesDone: 142_000_000, bytesTotal: 283_954_324, previous: 'update'});
  assert.equal(element('normal-controls').hidden, true);
  assert.equal(running.detail, 'Downloading the update');
  assert.equal(running.bytes, '142 MB of 284 MB (50%)');
  assert.equal(show('unpacking', {previous: 'runtime'}).detail, 'Checking and installing the update. This takes about half a minute.');
  const failed = show('failed', {reason: 'Cue\'s helper is still in use.', previous: 'unpacking'});
  assert.equal(element('normal-controls').hidden, false, 'a failed update leaves the old helper working');
  assert.equal(failed.primary, 'Retry');
  assert.equal(failed.announce, 'The update did not finish');
  assert.equal(show('done', {previous: 'smoke'}).announce, "Cue's helper is up to date");
  assert.equal(element('setup-card').hidden, true);
  // First-run setup gets its own heading and the model credits back.
  messages.get('cue-setup')!(setupView({phase: 'download', diskBytes: 3_834_972_052}));
  assert.equal(element('setup-title').textContent, 'Set up Cue');
  assert.equal(element('setup-credits').hidden, false);
  assert.equal(element('normal-controls').hidden, true);
});

test('with nothing left to download, setup says so and offers Continue', () => {
  const view = setupView({phase: 'download', diskBytes: 0});
  assert.equal(view.primary, 'Continue');
  assert.match(view.detail, /already on this Mac/);
  assert.doesNotMatch(view.detail, /0 MB/);
  assert.equal(setupView({phase: 'download', diskBytes: 3_834_972_052}).primary, 'Download');
});
