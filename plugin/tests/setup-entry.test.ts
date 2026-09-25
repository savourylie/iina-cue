import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {buildSync} from 'esbuild';
import {RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URL} from '../src/runtime-install';

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
  const release = JSON.parse(readFileSync('release/runtime-0.1.5.json', 'utf8')) as {size: number};
  assert.match(setup?.detail ?? '', new RegExp(String(models + release.size)));
  messages.get('start-setup')!({});
  // Preflight reads the Mac with sysctl, sw_vers and df first; those are not installs.
  const installs = () => execs.filter(({file}) => file === '/usr/bin/curl' || file === '/bin/sh');
  for (let i = 0; i < 50 && installs().length < 2; i++) await new Promise<void>(resolve => setImmediate(resolve));
  assert.ok(execs.some(({file, args}) => file === '/usr/sbin/sysctl' && args.includes('hw.memsize')));
  const [curl, unpack] = installs();
  assert.equal(curl.file, '/usr/bin/curl');
  assert.ok(curl.args.includes('-C'));
  assert.ok(curl.args.includes('--fail'));
  assert.equal(curl.args[curl.args.length - 1], RUNTIME_ARCHIVE_URL);
  assert.ok(curl.args.some(arg => arg.endsWith("/runtime.tar.xz.partial")));
  assert.equal(unpack.file, '/bin/sh');
  assert.ok(unpack.args.includes(RUNTIME_ARCHIVE_SHA256));
  const script = unpack.args[1];
  assert.match(script, /tar -xf/);
  assert.match(script, /installed/);
  const probe = spawnSync('/bin/sh', ['-c', script, 'cue-unpack', '/no/such/archive', '/no/such/runtime', 'abc'], {encoding: 'utf8'});
  assert.notEqual(probe.status, 0);
});
