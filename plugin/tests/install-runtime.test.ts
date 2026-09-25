import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {chmodSync, copyFileSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {installVerifiedArchive} from '../src/install-archive';
import {DEFAULT_RAM_BYTES, curlResumeArgs, maySwap, preflight, startInstall} from '../src/install-runtime';
import {installPublishedRuntime, RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URL} from '../src/runtime-install';

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
  assert.match(reason(preflight({...base, freeBytes: 10, bytesNeeded: 1000})), /1000 bytes/);
  assert.match(reason(preflight({...base, ramBytes: DEFAULT_RAM_BYTES - 1})), new RegExp(String(DEFAULT_RAM_BYTES)));
});

test('a busy helper is not swapped', () => {
  assert.deepEqual(maySwap({remuxActive: true, sessions: 0}), {ok: false, code: 'HELPER_RESTART_REQUIRED'});
  assert.deepEqual(maySwap({remuxActive: false, sessions: 1}), {ok: false, code: 'HELPER_RESTART_REQUIRED'});
  assert.deepEqual(maySwap({remuxActive: false, sessions: 0}), {ok: true});
});

test('curl resumes and is not a file shipped in the plugin', () => {
  assert.deepEqual(curlResumeArgs('https://github.com/savourylie/iina-cue/releases/download/runtime-0.1.5/runtime-0.1.5.tar.xz', '/tmp/part'), [
    '/usr/bin/curl', '-L', '--fail', '-C', '-', '-o', '/tmp/part',
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
    assert.equal(calls[0][calls[0].length - 1], RUNTIME_ARCHIVE_URL);
    assert.equal(calls[1][0], '/bin/sh');
    assert.ok(calls[1].includes(RUNTIME_ARCHIVE_SHA256));
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
