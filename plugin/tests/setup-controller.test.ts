import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {createSetupController} from '../src/setup-controller';
import {DEFAULT_RAM_BYTES, preflight, type PreflightFacts} from '../src/install-runtime';
import {readMacFacts} from '../src/runtime-install';

const facts: PreflightFacts = {
  arch: 'arm64', macos: '27.0', iina: '1.4.4', freeBytes: 9_000_000_000,
  ramBytes: DEFAULT_RAM_BYTES, minimumMacos: '27.0', bytesNeeded: 3_834_972_052,
};

test('sidebar ready posts the setup card and start-setup runs install then the helper actions', async () => {
  const calls: string[] = [];
  const posts: {showCard: boolean; primary: string | null; detail: string; ready: boolean}[] = [];
  const controller = createSetupController({
    rpc: async (method, path, body) => {
      calls.push(`${method} ${path} ${body?.action ?? ''}`);
      if (!calls.includes('install')) throw new Error('SETUP_REQUIRED');
      const done = calls.some((call) => call.endsWith(' start'));
      return {files_ready: done, bytes_total: 100, free_disk_bytes: 9_000_000_000, progress: {bytes_done: done ? 100 : 0, bytes_total: 100, phase: 'idle'}};
    },
    post: (view) => posts.push(view),
    facts: async () => facts,
    wait: async () => {},
    installRuntime: async () => { calls.push('install'); return {ok: true}; },
  });
  await controller.refresh();
  assert.equal(posts[0].showCard, true);
  assert.equal(posts[0].ready, false);
  assert.equal(posts[0].primary, 'Download');
  assert.match(posts[0].detail, /3834972052/);
  assert.equal(calls.includes('install'), false);
  await controller.start();
  assert.ok(calls.includes('install'));
  assert.ok(calls.includes('POST /v1/setup/actions start'));
  assert.ok(calls.includes('POST /v1/setup/actions smoke'));
});

test('low free disk does not start the download', async () => {
  let installed = false;
  const posts: {detail: string; primary: string | null}[] = [];
  const controller = createSetupController({
    rpc: async () => ({files_ready: false, free_disk_bytes: 10}),
    post: (view) => posts.push(view),
    facts: async () => facts,
    wait: async () => {},
    installRuntime: async () => { installed = true; return {ok: true}; },
  });
  await controller.start();
  assert.equal(installed, false);
  assert.match(posts[posts.length - 1].detail, /3834972052 bytes are required/);
  assert.equal(posts[posts.length - 1].primary, null);
});

test('a failed runtime install offers retry', async () => {
  const posts: {detail: string; primary: string | null}[] = [];
  const controller = createSetupController({
    rpc: async () => { throw new Error('SETUP_REQUIRED'); },
    post: (view) => posts.push(view),
    facts: async () => facts,
    wait: async () => {},
    installRuntime: async () => ({ok: false, reason: 'The runtime download stopped.'}),
  });
  await controller.start();
  assert.equal(posts[posts.length - 1].primary, 'Retry');
  assert.equal(posts[posts.length - 1].detail, 'The runtime download stopped.');
});

test('an unsupported Mac is posted without installing', async () => {
  let installed = false;
  const posts: {detail: string; primary: string | null}[] = [];
  const controller = createSetupController({
    rpc: async () => ({files_ready: false}),
    post: (view) => posts.push(view),
    facts: async () => ({...facts, arch: 'x86_64'}),
    wait: async () => {},
    installRuntime: async () => { installed = true; return {ok: true}; },
  });
  await controller.refresh();
  assert.match(posts[0].detail, /Apple Silicon/);
  assert.equal(posts[0].primary, null);
  await controller.start();
  assert.equal(installed, false);
});

test('a development pack shows Terminal steps and a general pack hides them', () => {
  const source = readFileSync('plugin/preferences.html', 'utf8');
  assert.match(source, /id="dev-setup" hidden/);
  const packed = execFileSync(process.execPath, ['--input-type=module', '-e', `
    import {preferencesForPack} from './scripts/preferences-pack.mjs';
    const source = ${JSON.stringify(source)};
    process.stdout.write(preferencesForPack(source, true) + '\\n---\\n' + preferencesForPack(source, false));
  `], {cwd: process.cwd(), encoding: 'utf8'});
  const [dev, general] = packed.split('\n---\n');
  assert.match(dev, /id="dev-setup"/);
  assert.doesNotMatch(dev, /id="dev-setup" hidden/);
  assert.match(dev, /scripts\/setup-dev/);
  assert.equal(general, source);
});

function helperFake(options: {phases: string[]; smokePasses?: boolean}) {
  const calls: string[] = [];
  let polls = 0;
  let smoked = false;
  let smokePolls = 0;
  const status = () => {
    const phase = options.phases[Math.min(polls, options.phases.length - 1)];
    const filesReady = phase === 'idle';
    return {
      files_ready: filesReady, bytes_total: 100, bytes_needed: filesReady ? 0 : 60, free_disk_bytes: 9_000_000_000,
      progress: {phase: smoked ? (smokePolls < 2 ? 'smoking' : 'smoke') : phase, bytes_done: filesReady ? 100 : 40, bytes_total: 100},
      smoke: smoked && smokePolls >= 2 ? {passed: options.smokePasses ?? true, reason: 'ok'} : null,
    };
  };
  return {
    calls,
    rpc: async (method: string, path: string, body?: Record<string, unknown>) => {
      calls.push(`${method} ${path} ${body?.action ?? ''}`.trim());
      if (method === 'GET') { polls++; if (smoked) smokePolls++; }
      if (body?.action === 'smoke') {
        calls.push(`smoke with files_ready=${status().files_ready}`);
        smoked = true;
      }
      return status();
    },
  };
}

test('smoke waits until the helper finishes the model download', async () => {
  const helper = helperFake({phases: ['idle-before', 'downloading', 'downloading', 'downloading', 'idle']});
  const posts: {progress: number | null; ready: boolean}[] = [];
  let waits = 0;
  const controller = createSetupController({
    rpc: helper.rpc, post: (view) => posts.push(view), facts: async () => facts,
    installRuntime: async () => { throw new Error('the helper already answers; no runtime download'); },
    wait: async () => { waits++; },
  });
  // 'idle-before' is a helper that has not started; POST start then reports downloading.
  await controller.start();
  assert.ok(waits >= 1);
  assert.ok(helper.calls.includes('smoke with files_ready=true'));
  assert.ok(!helper.calls.includes('smoke with files_ready=false'));
  assert.ok(posts.some((view) => view.progress === 40));
  assert.equal(posts[posts.length - 1].ready, true);
  assert.equal(posts.filter((view) => view.ready).length, 1);
});

test('an interrupted download offers retry, and retry resumes without reinstalling the runtime', async () => {
  const helper = helperFake({phases: ['interrupted']});
  const posts: {primary: string | null}[] = [];
  const controller = createSetupController({
    rpc: helper.rpc, post: (view) => posts.push(view), facts: async () => facts,
    installRuntime: async () => { throw new Error('no runtime download'); },
    wait: async () => {},
  });
  await controller.refresh();
  assert.equal(posts[0].primary, 'Retry');
  await controller.start();
  assert.ok(helper.calls.includes('POST /v1/setup/actions resume'));
  assert.ok(!helper.calls.some((call) => call.endsWith(' start')));
});

test('a second press while setup runs does not start a second download', async () => {
  let installs = 0;
  let release: () => void = () => {};
  const controller = createSetupController({
    rpc: async () => { throw new Error('SETUP_REQUIRED'); },
    post: () => {}, facts: async () => facts, wait: async () => {},
    installRuntime: () => { installs++; return new Promise((resolve) => { release = () => resolve({ok: false, reason: 'stop'}); }); },
  });
  const first = controller.start();
  for (let i = 0; i < 5; i++) await new Promise<void>((resolve) => setImmediate(resolve));
  await controller.start();
  release();
  await first;
  assert.equal(installs, 1);
});

test('Mac facts come from system tools, and an unreadable fact stays unknown', async () => {
  const answers: Record<string, string> = {
    '/usr/sbin/sysctl -n hw.optional.arm64': '1\n',
    '/usr/bin/sw_vers -productVersion': '27.0.1\n',
    '/usr/sbin/sysctl -n hw.memsize': '17179869184\n',
    '/bin/df -Pk /Users/cue/Library': 'Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk3s5 100 50 2048 50% /System/Volumes/Data\n',
  };
  const read = await readMacFacts({
    resolve: (path) => path.replace(/^~/, '/Users/cue'),
    exec: async (file, args) => {
      const out = answers[[file, ...args].join(' ')];
      return out === undefined ? {status: 1, stdout: '', stderr: 'no'} : {status: 0, stdout: out, stderr: ''};
    },
  });
  assert.deepEqual(read, {arch: 'arm64', macos: '27.0.1', freeBytes: 2048 * 1024, ramBytes: 17179869184});
  const unknown = await readMacFacts({resolve: () => null, exec: async () => ({status: 1})});
  assert.deepEqual(unknown, {arch: undefined, macos: undefined, freeBytes: undefined, ramBytes: undefined});
  assert.equal(preflight({...unknown, iina: '1.4.4', minimumMacos: '27.0', bytesNeeded: 1}).ok, true);
});
