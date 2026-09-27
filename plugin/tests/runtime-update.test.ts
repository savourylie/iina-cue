import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {copyFileSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readlinkSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {createSetupController, type SetupStatus} from '../src/setup-controller';
import {DEFAULT_RAM_BYTES, type PreflightFacts} from '../src/install-runtime';
import {installPublishedRuntime, RUNTIME_ARCHIVE_BYTES, RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URLS, RUNTIME_PARTIAL, RUNTIME_VERSION} from '../src/runtime-install';

const facts: PreflightFacts = {
  arch: 'arm64', macos: '27.0', iina: '1.4.4', freeBytes: 9_000_000_000,
  ramBytes: DEFAULT_RAM_BYTES, minimumMacos: '14.0', bytesNeeded: 3_834_972_052,
};
const ready: SetupStatus = {files_ready: true, bytes_total: 100, bytes_needed: 0, free_disk_bytes: 9e9, progress: {phase: 'idle', bytes_done: 100, bytes_total: 100}, smoke: {passed: true, reason: 'ok'}};
const runtime = {version: '0.1.9', bytes: 283_954_324};

/** A helper that answers setup requests as an installed one would, at a given version. */
function installedHelper(version: string, options: {installed?: boolean} = {}) {
  const state = {version, installed: options.installed ?? true, calls: [] as string[], smoked: 0};
  return {
    state,
    rpc: async (method: string, path: string, body?: Record<string, unknown>) => {
      state.calls.push(`${method} ${path} ${body?.action ?? ''}`.trim());
      if (body?.action === 'smoke') state.smoked++;
      return {...ready, progress: {...ready.progress, phase: 'idle'}};
    },
    helper: () => ({version: state.version, installed: state.installed}),
  };
}

test('an older installed helper is offered an update with its size, and nothing starts until the button', async () => {
  const helper = installedHelper('0.1.6');
  const posts: any[] = [];
  let installs = 0;
  const controller = createSetupController({
    rpc: helper.rpc, post: (view) => posts.push(view), facts: async () => facts, wait: async () => {},
    installRuntime: async () => { installs++; return {ok: true}; }, helper: helper.helper, runtime,
  });
  await controller.refresh();
  const offer = posts[posts.length - 1];
  assert.equal(offer.showCard, false, 'an offer is only a button, which the user can ignore');
  assert.equal(offer.showControls, true, 'captions keep working with the installed helper');
  assert.equal(offer.updateButton, 'Update Cue');
  assert.match(offer.updateHint, /284 MB download/);
  assert.equal(installs, 0);
  assert.deepEqual(helper.state.calls, ['GET /setup']);
});

test('the same or a newer version, a development checkout, or an unreported version is left alone', async () => {
  for (const [version, installed] of [['0.1.9', true], ['0.1.10', true], ['0.1.6', false], [null, true]] as const) {
    const helper = installedHelper(version as string, {installed});
    const posts: any[] = [];
    const controller = createSetupController({
      rpc: helper.rpc, post: (view) => posts.push(view), facts: async () => facts, wait: async () => {},
      installRuntime: async () => { throw new Error('must not install'); }, helper: helper.helper, runtime,
    });
    await controller.refresh();
    assert.equal(posts[posts.length - 1].ready, true, `${version} installed=${installed}`);
    assert.equal(posts[posts.length - 1].showCard, false);
  }
});

test('pressing Update replaces the runtime, then the new helper runs the test clip', async () => {
  const helper = installedHelper('0.1.6');
  const posts: any[] = [];
  const updates: boolean[] = [];
  const controller = createSetupController({
    rpc: helper.rpc, post: (view) => posts.push(view), facts: async () => facts, wait: async () => {},
    installRuntime: async (onProgress, onUnpack, update) => {
      updates.push(update);
      onProgress(142_000_000, runtime.bytes);
      // While the runtime is swapped, a sidebar refresh must not start the old helper again.
      assert.equal(controller.swapping(), true);
      const before = helper.state.calls.length;
      await controller.refresh();
      assert.equal(helper.state.calls.length, before);
      onUnpack();
      helper.state.version = '0.1.9';
      return {ok: true};
    },
    helper: helper.helper, runtime,
  });
  await controller.refresh();
  await controller.start();
  assert.deepEqual(updates, [true]);
  assert.equal(helper.state.smoked, 1, 'the new helper is tried before Cue calls itself ready');
  const running = posts.find((view) => view.bytes === '142 MB of 284 MB (50%)');
  assert.ok(running);
  assert.equal(running.showControls, true, 'each window turns its own captions off and on');
  assert.equal(running.detail, 'Downloading the update. Captions keep working meanwhile.');
  assert.equal(running.progress, 50);
  const installing = posts.find((view) => view.detail === 'Installing the update. Captions pause for about a minute.');
  assert.ok(installing);
  assert.equal(installing.indeterminate, true);
  const last = posts[posts.length - 1];
  assert.equal(last.ready, true);
  assert.equal(last.showCard, false);
  assert.equal(controller.swapping(), false);
});

test('a run reads the Mac\'s facts once, so progress is not held up behind the download', async () => {
  const helper = installedHelper('0.1.6');
  let factReads = 0;
  let finished = 0;
  const controller = createSetupController({
    rpc: helper.rpc, post: () => {}, facts: async () => { factReads++; return facts; }, wait: async () => {},
    installRuntime: async (onProgress, onUnpack) => {
      for (const done of [1e6, 2e6, 3e6]) onProgress(done, runtime.bytes);
      onUnpack();
      helper.state.version = '0.1.9';
      return {ok: true};
    },
    helper: helper.helper, runtime, updateFinished: () => { finished++; },
  });
  await controller.start();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(factReads, 1);
  assert.equal(finished, 1, 'windows are told the update ended, so their captions come back');
});

test('a refused or failed update keeps the old helper usable and offers Retry', async () => {
  const helper = installedHelper('0.1.6');
  const posts: any[] = [];
  const busy = "Cue's helper is still in use. Turn off AI subtitles in every IINA window and wait for any MKV copy to finish, then retry.";
  const controller = createSetupController({
    rpc: helper.rpc, post: (view) => posts.push(view), facts: async () => facts, wait: async () => {},
    installRuntime: async () => ({ok: false, reason: busy}), helper: helper.helper, runtime,
  });
  await controller.start();
  const last = posts[posts.length - 1];
  assert.equal(last.detail, busy);
  assert.equal(last.primary, 'Retry');
  assert.equal(last.showControls, true);
  assert.equal(helper.state.smoked, 0);
  // Reopening the sidebar offers the update again.
  await controller.refresh();
  assert.equal(posts[posts.length - 1].updateButton, 'Update Cue');
});

test('an updated runtime whose helper does not start says so, and Retry reinstalls it', async () => {
  const helper = installedHelper('0.1.6');
  let swapped = false;
  const posts: any[] = [];
  const controller = createSetupController({
    rpc: async (method, path, body) => { if (swapped) throw new Error('HELPER_DISCONNECTED'); return helper.rpc(method, path, body); },
    post: (view) => posts.push(view), facts: async () => facts, wait: async () => {},
    installRuntime: async () => { swapped = true; return {ok: true}; }, helper: helper.helper, runtime,
  });
  await controller.start();
  assert.equal(posts[posts.length - 1].detail, 'The updated helper did not start. Retry to install it again.');
  assert.equal(posts[posts.length - 1].primary, 'Retry');
});

/** A published-looking archive whose top directory is the version, like the real one. */
function makeArchive(root: string, marker: string) {
  const payload = join(root, `payload-${marker}`);
  mkdirSync(join(payload, `runtime-${RUNTIME_VERSION}`, 'bin'), {recursive: true});
  writeFileSync(join(payload, `runtime-${RUNTIME_VERSION}`, 'bin', 'cue-helper'), marker);
  const archive = join(root, `${marker}.tar.xz`);
  execFileSync('/usr/bin/tar', ['-cJf', archive, '-C', payload, `runtime-${RUNTIME_VERSION}`]);
  return {archive, sha: createHash('sha256').update(readFileSync(archive)).digest('hex')};
}

/**
 * Real files, the real unpack script. Only the published checksum is simulated:
 * the test archive stands in for the 284 MB one, so its own hash is substituted.
 */
function updateHarness(root: string, archive: {archive: string; sha: string}, options: {curlStatus?: number; shasum?: string} = {}) {
  const calls: string[] = [];
  const exec = async (file: string, args: string[]) => {
    const partial = join(root, RUNTIME_PARTIAL);
    if (file === '/usr/bin/curl') {
      calls.push('curl');
      if (options.curlStatus) return {status: options.curlStatus};
      copyFileSync(archive.archive, args[args.indexOf('-o') + 1]);
      return {status: 0};
    }
    if (file === '/usr/bin/stat') return existsSync(partial) ? {status: 0, stdout: `${RUNTIME_ARCHIVE_BYTES}\n`} : {status: 1, stdout: ''};
    if (file === '/usr/bin/shasum') { calls.push('verify'); return {status: 0, stdout: `${options.shasum ?? RUNTIME_ARCHIVE_SHA256}  ${partial}\n`}; }
    if (file === '/bin/sh' && args.includes(RUNTIME_ARCHIVE_SHA256)) {
      calls.push('unpack');
      args = args.map((arg) => (arg === RUNTIME_ARCHIVE_SHA256 ? archive.sha : arg));
    } else if (file === '/bin/sh') calls.push('clear');
    else calls.push(file);
    const result = spawnSync(file, args, {encoding: 'utf8'});
    return {status: result.status ?? 1, stdout: result.stdout, stderr: result.stderr};
  };
  return {calls, exec};
}

function installedTree(root: string) {
  mkdirSync(join(root, 'runtime', 'bin'), {recursive: true});
  writeFileSync(join(root, 'runtime', 'bin', 'cue-helper'), 'old');
  writeFileSync(join(root, 'installed'), '1\n');
  mkdirSync(join(root, 'cache', 'media'), {recursive: true});
  writeFileSync(join(root, 'cache', 'media', 'source.json'), 'cached captions');
  mkdirSync(join(root, 'checkout-models', 'gemma'), {recursive: true});
  writeFileSync(join(root, 'checkout-models', 'gemma', 'model'), 'weights');
  symlinkSync(join(root, 'checkout-models'), join(root, 'models'));
  // An older plugin's complete download of another version, under the old name.
  writeFileSync(join(root, 'runtime.tar.xz.partial'), 'runtime 0.1.6');
}

test('an update downloads and verifies first, stops the old helper, then swaps only the runtime', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cue-update-'));
  try {
    installedTree(root);
    const archive = makeArchive(root, 'new');
    const harness = updateHarness(root, archive);
    const result = await installPublishedRuntime({
      resolve: () => root, remuxActive: false, sessions: 0, exec: harness.exec,
      beforeSwap: async () => { harness.calls.push('stop helper'); return {ok: true}; },
    });
    assert.deepEqual(result, {ok: true});
    assert.deepEqual(harness.calls, ['clear', 'curl', 'verify', 'stop helper', 'unpack']);
    assert.equal(readFileSync(join(root, 'runtime', 'bin', 'cue-helper'), 'utf8'), 'new');
    // Models (here a symlink to a checkout) and the subtitle cache are untouched.
    assert.ok(lstatSync(join(root, 'models')).isSymbolicLink());
    assert.equal(readlinkSync(join(root, 'models')), join(root, 'checkout-models'));
    assert.equal(readFileSync(join(root, 'models', 'gemma', 'model'), 'utf8'), 'weights');
    assert.equal(readFileSync(join(root, 'cache', 'media', 'source.json'), 'utf8'), 'cached captions');
    assert.equal(existsSync(join(root, 'runtime.tar.xz.partial')), false, 'the stale download of another version is gone');
    assert.equal(existsSync(join(root, RUNTIME_PARTIAL)), false, 'the finished install deletes its archive');
    assert.equal(existsSync(join(root, 'runtime.previous')), false);
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('a helper in use keeps its runtime; the verified download waits, and Retry does not fetch it again', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cue-update-busy-'));
  try {
    installedTree(root);
    const archive = makeArchive(root, 'new');
    const busy = updateHarness(root, archive);
    const refused = await installPublishedRuntime({
      resolve: () => root, remuxActive: false, sessions: 0, exec: busy.exec, busyReason: 'in use',
      beforeSwap: async () => ({ok: false, reason: 'in use'}),
    });
    assert.deepEqual(refused, {ok: false, reason: 'in use'});
    assert.ok(!busy.calls.includes('unpack'));
    assert.equal(readFileSync(join(root, 'runtime', 'bin', 'cue-helper'), 'utf8'), 'old');
    assert.ok(existsSync(join(root, RUNTIME_PARTIAL)), 'the verified download is kept');
    const retry = updateHarness(root, archive);
    const updated = await installPublishedRuntime({
      resolve: () => root, remuxActive: false, sessions: 0, exec: retry.exec,
      beforeSwap: async () => ({ok: true}),
    });
    assert.deepEqual(updated, {ok: true});
    assert.deepEqual(retry.calls, ['clear', 'verify', 'unpack']);
    assert.equal(readFileSync(join(root, 'runtime', 'bin', 'cue-helper'), 'utf8'), 'new');
    // This window's own captions or MKV copy refuse before anything is downloaded.
    const local = await installPublishedRuntime({
      resolve: () => root, remuxActive: false, sessions: 1, busyReason: 'in use',
      exec: async () => { throw new Error('must not run'); }, beforeSwap: async () => ({ok: true}),
    });
    assert.deepEqual(local, {ok: false, reason: 'in use'});
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('a failed download or a checksum mismatch never stops the old helper or touches its runtime', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cue-update-bad-'));
  try {
    installedTree(root);
    const archive = makeArchive(root, 'new');
    let stops = 0;
    const beforeSwap = async () => { stops++; return {ok: true as const}; };
    const offline = updateHarness(root, archive, {curlStatus: 6});
    const stopped = await installPublishedRuntime({resolve: () => root, remuxActive: false, sessions: 0, exec: offline.exec, beforeSwap});
    assert.deepEqual(stopped, {ok: false, reason: 'The runtime download stopped.'});
    assert.equal(offline.calls.filter((call) => call === 'curl').length, RUNTIME_ARCHIVE_URLS.length);
    const corrupt = updateHarness(root, archive, {shasum: '0'.repeat(64)});
    const mismatch = await installPublishedRuntime({resolve: () => root, remuxActive: false, sessions: 0, exec: corrupt.exec, beforeSwap});
    assert.deepEqual(mismatch, {ok: false, reason: 'The runtime download does not match the published checksum.'});
    assert.ok(!corrupt.calls.includes('unpack'));
    assert.equal(existsSync(join(root, RUNTIME_PARTIAL)), false, 'a bad download is removed so Retry fetches it again');
    assert.equal(stops, 0);
    assert.equal(readFileSync(join(root, 'runtime', 'bin', 'cue-helper'), 'utf8'), 'old');
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('the required runtime version is the pinned release', () => {
  const manifest = JSON.parse(readFileSync(resolve('release', `runtime-${RUNTIME_VERSION}.json`), 'utf8'));
  assert.equal(manifest.version, RUNTIME_VERSION);
  assert.equal(manifest.sha256, RUNTIME_ARCHIVE_SHA256);
  assert.equal(manifest.size, RUNTIME_ARCHIVE_BYTES);
  for (const url of RUNTIME_ARCHIVE_URLS) assert.ok(url.endsWith(`/runtime-${RUNTIME_VERSION}.tar.xz`), url);
  const helper = readFileSync('helper/src/cue/bootstrap.py', 'utf8').match(/^HELPER_VERSION = "([^"]+)"$/m)?.[1];
  assert.equal(helper, RUNTIME_VERSION, 'the checkout helper and the pinned runtime are the same version');
});

test('an update on a Mac with little free space is not mistaken for a first-run model download', async () => {
  const helper = installedHelper('0.1.6');
  const posts: any[] = [];
  const controller = createSetupController({
    // 2 GB free: enough for the runtime, not for the 3.6 GB of models an install without them needs.
    rpc: async (method, path, body) => ({...(await helper.rpc(method, path, body)), free_disk_bytes: 2_000_000_000}),
    post: (view) => posts.push(view), facts: async () => ({...facts, freeBytes: 2_000_000_000}), wait: async () => {},
    installRuntime: async (onProgress) => { onProgress(1, runtime.bytes); helper.state.version = '0.1.9'; return {ok: true}; },
    helper: helper.helper, runtime,
  });
  await controller.start();
  assert.ok(!posts.some((view) => /disk space/.test(view.detail)), posts.map((view) => view.detail).join(' | '));
  assert.equal(posts[posts.length - 1].ready, true);
});
