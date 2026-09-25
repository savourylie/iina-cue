import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {buildSync} from 'esbuild';
import {RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URLS, RUNTIME_PARTIAL, RUNTIME_VERSION} from '../src/runtime-install';

test('sidebar ready posts setup and start-setup runs the published install', async () => {
  const events = new Map<string, () => void>();
  const messages = new Map<string, (data: unknown) => void>();
  const posted: [string, {showCard?: boolean; detail?: string; primary?: string | null}][] = [];
  const execs: {file: string; args: string[]}[] = [];
  const source = buildSync({
    entryPoints: ['plugin/src/main.ts'],
    bundle: true,
    write: false,
    format: 'iife',
    platform: 'neutral',
    define: {CUE_BOOTSTRAP_DEFAULT: '"/fixture/helper"'},
  }).outputFiles[0].text;
  const iina = {
    menu: {
      item: (title: string, action: () => void) => ({title, action, items: [] as unknown[], addSubMenuItem(item: unknown) { this.items.push(item); return this; }}),
      addItem: () => {},
    },
    event: {on: (name: string, callback: () => void) => { events.set(name, callback); return name; }},
    mpv: {getString: () => '55', getNumber: () => 0, getFlag: () => false, set: () => {}, command: () => {}, getNative: () => []},
    preferences: {get: () => undefined},
    file: {exists: () => false, write: () => {}},
    core: {osd: () => {}},
    console: {log: () => {}},
    utils: {
      resolvePath(path: string) { return path.replace(/^~/, '/Users/cue'); },
      exec: async (file: string, args: string[]) => {
        execs.push({file, args});
        if (file === '/usr/bin/curl') return {status: 0, stdout: '', stderr: ''};
        return {status: 2, stdout: '', stderr: 'SHA256_MISMATCH\n'};
      },
      chooseFile: async () => '',
      prompt: async () => '',
      ask: async () => false,
    },
    sidebar: {
      loadFile: () => {},
      show: () => {},
      onMessage: (name: string, callback: (data: unknown) => void) => { messages.set(name, callback); },
      postMessage: (name: string, data: {showCard?: boolean; detail?: string; primary?: string | null}) => { posted.push([name, data]); },
    },
  };
  vm.runInNewContext(source, {iina, setInterval: () => 1, setTimeout: () => 1, clearTimeout: () => {}, clearInterval: () => {}});
  events.get('iina.window-loaded')!();
  messages.get('ready')!({});
  for (let i = 0; i < 20 && !posted.some(([name]) => name === 'cue-setup'); i++) await new Promise<void>(resolve => setImmediate(resolve));
  const setup = posted.filter(([name]) => name === 'cue-setup').pop()?.[1];
  assert.equal(setup?.showCard, true);
  assert.equal(setup?.primary, 'Download');
  const manifest = JSON.parse(readFileSync('models/manifest.json', 'utf8')) as {assets: {files: {bytes: number}[]}[]};
  const models = manifest.assets.reduce((sum, asset) => sum + asset.files.reduce((inner, file) => inner + file.bytes, 0), 0);
  const release = JSON.parse(readFileSync('release/runtime-0.1.9.json', 'utf8')) as {size: number};
  assert.equal(setup?.detail, `Needs about ${((models + release.size) / 1e9).toFixed(1)} GB of free disk space.`);
  messages.get('start-setup')!({});
  // Preflight reads the Mac with sysctl, sw_vers and df first; those are not installs.
  const installs = () => execs.filter(({file, args}) => file === '/usr/bin/curl' || (file === '/bin/sh' && args.includes(RUNTIME_ARCHIVE_SHA256)));
  for (let i = 0; i < 50 && installs().length < 2; i++) await new Promise<void>(resolve => setImmediate(resolve));
  assert.ok(execs.some(({file, args}) => file === '/usr/sbin/sysctl' && args.includes('hw.memsize')));
  const [curl, unpack] = installs();
  assert.equal(curl.file, '/usr/bin/curl');
  assert.ok(curl.args.includes('-C'));
  assert.ok(curl.args.includes('--fail'));
  assert.equal(curl.args[curl.args.length - 1], RUNTIME_ARCHIVE_URLS[0]);
  assert.ok(curl.args.some(arg => arg.endsWith(`/${RUNTIME_PARTIAL}`)));
  // Downloads of other runtime versions are cleared before this one starts.
  const cleared = execs.findIndex(({file, args}) => file === '/bin/sh' && args[1]?.includes('runtime.tar.xz.partial'));
  assert.ok(cleared >= 0 && cleared < execs.findIndex(({file}) => file === '/usr/bin/curl'));
  assert.equal(unpack.file, '/bin/sh');
  assert.ok(unpack.args.includes(RUNTIME_ARCHIVE_SHA256));
  const script = unpack.args[1];
  assert.match(script, /tar -xf/);
  assert.match(script, /installed/);
  const probe = spawnSync('/bin/sh', ['-c', script, 'cue-unpack', '/no/such/archive', '/no/such/runtime', 'abc'], {encoding: 'utf8'});
  assert.notEqual(probe.status, 0);
});

test('with a running helper, setup calls /v1/setup once-prefixed and does not download the runtime again', async () => {
  const events = new Map<string, () => void>();
  const messages = new Map<string, (data: unknown) => void>();
  const posted: [string, {showCard?: boolean; ready?: boolean; primary?: string | null}][] = [];
  const execs: string[] = [];
  const urls: string[] = [];
  let smoked = false;
  const source = buildSync({
    entryPoints: ['plugin/src/main.ts'], bundle: true, write: false, format: 'iife', platform: 'neutral',
    define: {CUE_BOOTSTRAP_DEFAULT: '""'},
  }).outputFiles[0].text;
  const installed = new Set(['~/Library/Application Support/Cue/installed', '~/Library/Application Support/Cue/runtime/bin/cue-helper']);
  const status = () => ({
    instance_id: 'helper-1', files_ready: true, bytes_total: 100, bytes_needed: 0, free_disk_bytes: 9e9,
    progress: {phase: smoked ? 'smoke' : 'idle', bytes_done: 100, bytes_total: 100},
    smoke: smoked ? {passed: true, reason: 'ok'} : null,
  });
  const answer = (url: string, body?: {action?: string}) => {
    urls.push(url);
    if (url.endsWith('/v1/clients')) return {data: {instance_id: 'helper-1', client_id: 'client-1'}};
    if (url.endsWith('/v1/setup')) return {data: status()};
    if (url.endsWith('/v1/setup/actions')) { if (body?.action === 'smoke') smoked = true; return {data: status()}; }
    return {data: {instance_id: 'helper-1', error: {code: 'NOT_FOUND'}}};
  };
  const iina = {
    menu: {
      item: (title: string, action: () => void) => ({title, action, items: [] as unknown[], addSubMenuItem(item: unknown) { this.items.push(item); return this; }}),
      addItem: () => {},
    },
    event: {on: (name: string, callback: () => void) => { events.set(name, callback); return name; }},
    mpv: {getString: () => '55', getNumber: () => 0, getFlag: () => false, set: () => {}, command: () => {}, getNative: () => []},
    preferences: {get: () => undefined},
    file: {exists: (path: string) => installed.has(path), write: () => {}},
    core: {osd: () => {}},
    console: {log: () => {}},
    http: {
      get: async (url: string) => answer(url),
      post: async (url: string, options: {data: {payload: string}}) => answer(url, JSON.parse(options.data.payload)),
      put: async (url: string) => answer(url),
      delete: async (url: string) => answer(url),
    },
    utils: {
      resolvePath(path: string) { return path.replace(/^~/, '/Users/cue'); },
      exec: async (file: string, args: string[]) => {
        execs.push(file);
        if (file === '/bin/sh' && args[1] === 'ensure') {
          return {status: 0, stderr: '', stdout: JSON.stringify({protocol_version: 1, host: '127.0.0.1', port: 4242, token: 'a'.repeat(64), instance_id: 'helper-1'})};
        }
        return {status: 1, stdout: '', stderr: ''};
      },
      chooseFile: async () => '', prompt: async () => '', ask: async () => false,
    },
    sidebar: {
      loadFile: () => {}, show: () => {},
      onMessage: (name: string, callback: (data: unknown) => void) => { messages.set(name, callback); },
      postMessage: (name: string, data: {showCard?: boolean; ready?: boolean; primary?: string | null}) => { posted.push([name, data]); },
    },
  };
  vm.runInNewContext(source, {iina, setInterval: () => 1, setTimeout: () => 1, clearTimeout: () => {}, clearInterval: () => {}});
  events.get('iina.window-loaded')!();
  messages.get('ready')!({});
  const setupPosts = () => posted.filter(([name]) => name === 'cue-setup').map(([, view]) => view);
  for (let i = 0; i < 50 && setupPosts().length === 0; i++) await new Promise<void>(resolve => setImmediate(resolve));
  // Nothing is left to fetch, so setup offers to continue straight to the test clip.
  assert.equal(setupPosts()[setupPosts().length - 1]?.primary, 'Continue');
  messages.get('start-setup')!({});
  for (let i = 0; i < 100 && !setupPosts().some((view) => view.ready); i++) await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(setupPosts()[setupPosts().length - 1]?.ready, true);
  const setupUrls = urls.filter((url) => url.includes('/setup'));
  assert.ok(setupUrls.includes('http://127.0.0.1:4242/v1/setup'));
  assert.ok(setupUrls.includes('http://127.0.0.1:4242/v1/setup/actions'));
  assert.ok(!urls.some((url) => url.includes('/v1/v1/')), urls.join('\n'));
  assert.ok(!execs.includes('/usr/bin/curl'), 'a running helper means the runtime is not downloaded again');
});

test('an installed older helper is offered the update, and Update stops it only after the verified download', async () => {
  const events = new Map<string, () => void>();
  const messages = new Map<string, (data: unknown) => void>();
  const posted: [string, any][] = [];
  const steps: string[] = [];
  let swapped = false;
  let stopping = false;
  let smoked = false;
  const source = buildSync({
    entryPoints: ['plugin/src/main.ts'], bundle: true, write: false, format: 'iife', platform: 'neutral',
    define: {CUE_BOOTSTRAP_DEFAULT: '""'},
  }).outputFiles[0].text;
  const installed = new Set(['~/Library/Application Support/Cue/installed', '~/Library/Application Support/Cue/runtime/bin/cue-helper']);
  const helper = () => swapped ? {instance_id: 'helper-new', port: 5252, helper_version: RUNTIME_VERSION} : {instance_id: 'helper-old', port: 4242, helper_version: '0.1.6'};
  const status = () => ({
    instance_id: helper().instance_id, files_ready: true, bytes_total: 100, bytes_needed: 0, free_disk_bytes: 9e9,
    progress: {phase: 'idle', bytes_done: 100, bytes_total: 100}, smoke: swapped && !smoked ? null : {passed: true, reason: 'ok'},
  });
  const answer = (method: string, url: string, body?: {action?: string}) => {
    const {pathname, port} = new URL(url);
    if (Number(port) !== helper().port || stopping) throw new Error('connection refused');
    const instance_id = helper().instance_id;
    if (pathname === '/v1/clients') return {data: {instance_id, client_id: `client-${instance_id}`}};
    if (pathname === '/v1/client' && method === 'DELETE') { steps.push('release lease'); return {data: {instance_id, ok: true}}; }
    if (pathname === '/v1/shutdown') { steps.push('shutdown'); stopping = true; return {data: {instance_id, stopping: true}}; }
    if (pathname === '/v1/setup/actions' && body?.action === 'smoke') { steps.push(`smoke on ${instance_id}`); smoked = true; }
    return {data: status()};
  };
  const iina = {
    menu: {item: (title: string, action: () => void) => ({title, action, items: [] as unknown[], addSubMenuItem(item: unknown) { this.items.push(item); return this; }}), addItem: () => {}},
    event: {on: (name: string, callback: () => void) => { events.set(name, callback); return name; }},
    mpv: {getString: () => '55', getNumber: () => 0, getFlag: () => false, set: () => {}, command: () => {}, getNative: () => []},
    preferences: {get: () => undefined},
    file: {exists: (path: string) => installed.has(path), write: () => {}},
    core: {osd: () => {}},
    console: {log: () => {}},
    http: {
      get: async (url: string) => answer('GET', url),
      post: async (url: string, options: {data: {payload: string}}) => answer('POST', url, JSON.parse(options.data.payload)),
      put: async (url: string) => answer('PUT', url),
      delete: async (url: string) => answer('DELETE', url),
    },
    utils: {
      resolvePath(path: string) { return path.replace(/^~/, '/Users/cue'); },
      exec: async (file: string, args: string[]) => {
        if (file === '/bin/sh' && args[1] === 'ensure') {
          steps.push(`start ${helper().helper_version}`);
          stopping = false;
          return {status: 0, stderr: '', stdout: JSON.stringify({protocol_version: 1, host: '127.0.0.1', token: 'a'.repeat(64), ...helper()})};
        }
        if (file === '/usr/bin/curl') { steps.push('download'); return {status: 0}; }
        if (file === '/usr/bin/shasum') { steps.push('verify'); return {status: 0, stdout: `${RUNTIME_ARCHIVE_SHA256}  ${args[2]}\n`}; }
        if (file === '/bin/sh' && args.includes(RUNTIME_ARCHIVE_SHA256)) { steps.push('swap runtime'); swapped = true; return {status: 0}; }
        return {status: 1, stdout: '', stderr: ''};
      },
      chooseFile: async () => '', prompt: async () => '', ask: async () => false,
    },
    sidebar: {
      loadFile: () => {}, show: () => {},
      onMessage: (name: string, callback: (data: unknown) => void) => { messages.set(name, callback); },
      postMessage: (name: string, data: any) => { posted.push([name, data]); },
    },
  };
  vm.runInNewContext(source, {iina, setInterval: () => 1, setTimeout: () => 1, clearTimeout: () => {}, clearInterval: () => {}});
  events.get('iina.window-loaded')!();
  messages.get('ready')!({});
  const setupPosts = () => posted.filter(([name]) => name === 'cue-setup').map(([, view]) => view);
  for (let i = 0; i < 50 && !setupPosts().some((view) => view.primary === 'Update'); i++) await new Promise<void>(resolve => setImmediate(resolve));
  const offer = setupPosts().find((view) => view.primary === 'Update');
  assert.ok(offer, JSON.stringify(setupPosts()));
  assert.equal(offer.title, "Update Cue's helper");
  assert.equal(offer.showControls, true);
  assert.ok(!steps.includes('download'), 'nothing is downloaded before the button');
  messages.get('start-setup')!({});
  for (let i = 0; i < 200 && !setupPosts().some((view) => view.ready); i++) await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(setupPosts()[setupPosts().length - 1].ready, true, steps.join(' > '));
  assert.deepEqual(steps, [
    'start 0.1.6', 'download', 'verify', 'release lease', 'shutdown', 'swap runtime', `start ${RUNTIME_VERSION}`, 'smoke on helper-new',
  ]);
  // The new helper's speech models are listed without reopening the sidebar.
  const finished = posted.findIndex(([name, view]) => name === 'cue-setup' && view.ready);
  for (let i = 0; i < 50 && !posted.slice(finished).some(([name]) => name === 'cue-models'); i++) await new Promise<void>(resolve => setImmediate(resolve));
  assert.ok(posted.slice(finished).some(([name]) => name === 'cue-models'));
});
