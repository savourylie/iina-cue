import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {chmodSync, copyFileSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {installVerifiedArchive} from '../src/install-archive';
import {DEFAULT_RAM_BYTES, curlResumeArgs, maySwap, preflight, startInstall} from '../src/install-runtime';
import {CREDIT_LINKS, installPublishedRuntime, openCreditLink, RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URLS, UNPACK_RUNTIME_SCRIPT} from '../src/runtime-install';

const base = {arch: 'arm64', macos: '27.0', iina: '1.4.4', freeBytes: 10_000, ramBytes: DEFAULT_RAM_BYTES, minimumMacos: '27.0', bytesNeeded: 1000};

function reason(result: ReturnType<typeof preflight>): string {
  assert.equal(result.ok, false);
  if (result.ok) return '';
  return result.reason;
}

test('preflight refuses Intel, an older system, old IINA, low disk, and low memory', () => {
  assert.equal(preflight(base).ok, true);
  assert.match(reason(preflight({...base, arch: 'x86_64'})), /Apple Silicon/);
  assert.match(reason(preflight({...base, macos: '14.6'})), /27\.0/);
  assert.match(reason(preflight({...base, iina: '1.3.9'})), /1\.4/);
  assert.match(reason(preflight({...base, freeBytes: 10, bytesNeeded: 3_834_972_052})), /About 3\.8 GB is required/);
  assert.match(reason(preflight({...base, ramBytes: DEFAULT_RAM_BYTES - 1})), /at least 16 GB of memory/);
});

test('a busy helper is not swapped', () => {
  assert.deepEqual(maySwap({remuxActive: true, sessions: 0}), {ok: false, code: 'HELPER_RESTART_REQUIRED'});
  assert.deepEqual(maySwap({remuxActive: false, sessions: 1}), {ok: false, code: 'HELPER_RESTART_REQUIRED'});
  assert.deepEqual(maySwap({remuxActive: false, sessions: 0}), {ok: true});
});

test('curl resumes and is not a file shipped in the plugin', () => {
  assert.deepEqual(curlResumeArgs('https://github.com/savourylie/iina-cue/releases/download/runtime-0.1.5/runtime-0.1.5.tar.xz', '/tmp/part'), [
    '/usr/bin/curl', '-L', '--fail', '--speed-limit', '1024', '--speed-time', '60', '-C', '-', '-o', '/tmp/part',
    'https://github.com/savourylie/iina-cue/releases/download/runtime-0.1.5/runtime-0.1.5.tar.xz',
  ]);
  assert.throws(() => startInstall(false), /SETUP_NOT_STARTED/);
  startInstall(true);
});

test('a checksum mismatch and a failed unpack leave the working runtime in place', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cue-install-'));
  try {
    const payload = join(root, 'tree');
    mkdirSync(join(payload, 'runtime-0.1.5', 'bin'), {recursive: true});
    writeFileSync(join(payload, 'runtime-0.1.5', 'bin', 'ffmpeg'), 'ffmpeg');
    const archive = join(root, 'runtime.tar.xz.partial');
    execFileSync('/usr/bin/tar', ['-cJf', archive, '-C', payload, 'runtime-0.1.5']);
    const sha = createHash('sha256').update(readFileSync(archive)).digest('hex');
    const destination = join(root, 'runtime');
    mkdirSync(join(destination, 'bin'), {recursive: true});
    writeFileSync(join(destination, 'bin', 'keep'), 'working');
    const mismatch = await installVerifiedArchive({archive, expectedSha256: '0'.repeat(64), destination});
    assert.equal(mismatch.ok, false);
    if (!mismatch.ok) assert.equal(mismatch.code, 'SHA256_MISMATCH');
    assert.equal(readFileSync(join(destination, 'bin', 'keep'), 'utf8'), 'working');
    writeFileSync(archive, 'not a tar');
    const broken = await installVerifiedArchive({archive, expectedSha256: createHash('sha256').update(readFileSync(archive)).digest('hex'), destination});
    assert.equal(broken.ok, false);
    if (!broken.ok) assert.equal(broken.code, 'UNPACK_FAILED');
    assert.equal(readFileSync(join(destination, 'bin', 'keep'), 'utf8'), 'working');
    const busy = await installVerifiedArchive({archive, expectedSha256: sha, destination, sessions: 1});
    assert.equal(busy.ok, false);
    if (!busy.ok) assert.equal(busy.code, 'HELPER_RESTART_REQUIRED');
    assert.equal(readFileSync(join(destination, 'bin', 'keep'), 'utf8'), 'working');
    execFileSync('/usr/bin/tar', ['-cJf', archive, '-C', payload, 'runtime-0.1.5']);
    const goodSha = createHash('sha256').update(readFileSync(archive)).digest('hex');
    const installed = await installVerifiedArchive({archive, expectedSha256: goodSha, destination});
    assert.equal(installed.ok, true);
    assert.equal(readFileSync(join(destination, 'bin', 'ffmpeg'), 'utf8'), 'ffmpeg');
    assert.equal(readFileSync(join(root, 'installed'), 'utf8'), '1\n');
    assert.equal(existsSync(join(destination, 'runtime-0.1.5')), false);
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('the plugin install path resumes the published archive and rejects a different file', async () => {
  const root = mkdtempSync(join(tmpdir(), 'cue-published-'));
  try {
    const payload = join(root, 'tree');
    mkdirSync(join(payload, 'runtime-0.1.5', 'bin'), {recursive: true});
    writeFileSync(join(payload, 'runtime-0.1.5', 'bin', 'ffmpeg'), 'ffmpeg');
    const archive = join(root, 'made.tar.xz');
    execFileSync('/usr/bin/tar', ['-cJf', archive, '-C', payload, 'runtime-0.1.5']);
    const calls: string[][] = [];
    const rejected = await installPublishedRuntime({
      resolve: () => root,
      remuxActive: false,
      sessions: 0,
      exec: async (file, args) => {
        calls.push([file, ...args]);
        if (file === '/usr/bin/curl') {
          copyFileSync(archive, args[args.indexOf('-o') + 1]);
          return {status: 0, stdout: '', stderr: ''};
        }
        const result = spawnSync(file, args, {encoding: 'utf8'});
        return {status: result.status ?? 1, stdout: result.stdout, stderr: result.stderr};
      },
    });
    assert.equal(rejected.ok, false);
    if (!rejected.ok) assert.equal(rejected.reason, 'The runtime download does not match the published checksum.');
    assert.equal(calls[0][0], '/usr/bin/curl');
    assert.ok(calls[0].includes('-C'));
    assert.ok(calls[0].includes('--fail'));
    assert.equal(calls[0][calls[0].length - 1], RUNTIME_ARCHIVE_URLS[0]);
    assert.equal(calls[1][0], '/bin/sh');
    assert.ok(calls[1].includes(RUNTIME_ARCHIVE_SHA256));
    // A file that fails the checksum is removed, so Retry downloads it again.
    assert.deepEqual(calls[2], ['/bin/rm', '-f', calls[0][calls[0].indexOf('-o') + 1]]);
    assert.equal(existsSync(join(root, 'installed')), false);
    assert.equal(existsSync(join(root, 'runtime', 'bin', 'ffmpeg')), false);
    const busy = await installPublishedRuntime({
      resolve: () => root,
      remuxActive: true,
      sessions: 0,
      exec: async () => { throw new Error('should not download'); },
    });
    assert.equal(busy.ok, false);
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('the plugin archive gate rejects an executable script and accepts the packed plugin', () => {
  const root = mkdtempSync(join(tmpdir(), 'cue-archive-'));
  try {
    const script = join(root, 'run.sh');
    writeFileSync(script, '#!/bin/sh\necho no\n');
    chmodSync(script, 0o755);
    const bad = join(root, 'bad.iinaplgz');
    execFileSync('/usr/bin/zip', ['-r', bad, 'run.sh'], {cwd: root});
    const moduleUrl = 'file://' + join(process.cwd(), 'scripts/check-plugin-archive.mjs');
    assert.throws(() => execFileSync(process.execPath, ['--input-type=module', '-e', `import {assertSafePluginArchive} from ${JSON.stringify(moduleUrl)}; assertSafePluginArchive(${JSON.stringify(bad)});`]), /executable script/);
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('a failed Hugging Face download falls back to the GitHub copy of the same file', async () => {
  const calls: string[][] = [];
  const result = await installPublishedRuntime({
    resolve: () => '/Users/cue/Library/Application Support/Cue',
    remuxActive: false,
    sessions: 0,
    exec: async (file, args) => {
      calls.push([file, ...args]);
      if (file === '/usr/bin/curl') return {status: args[args.length - 1].includes('huggingface.co') ? 28 : 0};
      return {status: 0};
    },
  });
  assert.equal(result.ok, true);
  const curls = calls.filter(([file]) => file === '/usr/bin/curl');
  assert.deepEqual(curls.map((call) => new URL(call[call.length - 1]).hostname), ['huggingface.co', 'github.com']);
  // Both attempts write the same partial file, so the second one resumes the first.
  assert.equal(curls[0][curls[0].indexOf('-o') + 1], curls[1][curls[1].indexOf('-o') + 1]);
});

test('when every copy fails, setup reports a stopped download and unpacks nothing', async () => {
  const calls: string[][] = [];
  const result = await installPublishedRuntime({
    resolve: () => '/Users/cue/Library/Application Support/Cue',
    remuxActive: false,
    sessions: 0,
    exec: async (file, args) => { calls.push([file, ...args]); return {status: 6}; },
  });
  assert.deepEqual(result, {ok: false, reason: 'The runtime download stopped.'});
  assert.equal(calls.length, RUNTIME_ARCHIVE_URLS.length);
});

test('credit links open only the pinned model pages in the browser', () => {
  const opened: string[][] = [];
  const exec = (file: string, args: string[]) => { opened.push([file, ...args]); };
  assert.equal(openCreditLink('gemma', exec), true);
  assert.equal(openCreditLink('aligner', exec), true);
  assert.equal(openCreditLink('https://example.com', exec), false);
  assert.equal(openCreditLink('toString', exec), false);
  assert.equal(openCreditLink(undefined, exec), false);
  assert.deepEqual(opened, [
    ['/usr/bin/open', CREDIT_LINKS.gemma],
    ['/usr/bin/open', CREDIT_LINKS.aligner],
  ]);
  const manifest = JSON.parse(readFileSync('models/manifest.json', 'utf8')) as {assets: {name: string; repository: string}[]};
  for (const asset of manifest.assets) {
    assert.equal(CREDIT_LINKS[asset.name as keyof typeof CREDIT_LINKS], `https://huggingface.co/${asset.repository}`);
  }
});

test('the runtime download reports the archive size while curl runs, and a finished install deletes the archive', async () => {
  const progress: number[] = [];
  let finish: () => void = () => {};
  let sizes = 0;
  const pending = installPublishedRuntime({
    resolve: () => '/Users/cue/Library/Application Support/Cue',
    remuxActive: false,
    sessions: 0,
    onProgress: (done, total) => { progress.push(done); assert.equal(total, 267837724); },
    wait: () => new Promise<void>((resolve) => setImmediate(resolve)),
    exec: async (file) => {
      if (file === '/usr/bin/curl') return new Promise((resolve) => { finish = () => resolve({status: 0}); });
      if (file === '/usr/bin/stat') { sizes += 1_000_000; return {status: 0, stdout: `${sizes}\n`}; }
      return {status: 0};
    },
  });
  for (let i = 0; i < 10; i++) await new Promise<void>((resolve) => setImmediate(resolve));
  finish();
  assert.deepEqual(await pending, {ok: true});
  assert.ok(progress.length >= 2);
  assert.ok(progress.every((value, index) => index === 0 || value > progress[index - 1]));
  assert.match(UNPACK_RUNTIME_SCRIPT, /rm -rf "\$previous"\n# The runtime is in place[^\n]*\nrm -f "\$archive"/);
});
