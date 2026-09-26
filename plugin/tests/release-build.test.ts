import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {homedir, tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {INSTALLED_SUPPORT, planLaunch} from '../src/launch';

const root = resolve(import.meta.dirname, '../..');
const marker = `${INSTALLED_SUPPORT}/installed`;
const launcher = `${INSTALLED_SUPPORT}/runtime/bin/cue-helper`;
const absoluteLauncher = '/Users/cue/Library/Application Support/Cue/runtime/bin/cue-helper';
const resolvePath = (path: string) => path === launcher ? absoluteLauncher : null;

test('with no development launcher and nothing installed, the general-user pack asks for setup', () => {
  // Even a file at a path that looks like a checkout must not be used: the pack has no such path.
  assert.throws(() => planLaunch({preference: '', devBootstrap: '', exists: () => false, resolve: resolvePath}), /SETUP_REQUIRED/);
  assert.throws(() => planLaunch({preference: undefined, devBootstrap: '', exists: (path) => path === '', resolve: resolvePath}), /SETUP_REQUIRED/);
});

test('the general-user pack starts the installed runtime, and an explicit preference still overrides it', () => {
  const installed = (path: string) => path === marker || path === launcher;
  assert.deepEqual(planLaunch({preference: '', devBootstrap: '', exists: installed, resolve: resolvePath}), {file: '/bin/sh', args: [absoluteLauncher, 'ensure'], mode: 'installed'});
  assert.deepEqual(
    planLaunch({preference: '/custom/helper', devBootstrap: '', exists: (path) => path === '/custom/helper', resolve: resolvePath}),
    {file: '/custom/helper', args: ['ensure'], mode: 'preference'},
  );
});

const iinaPack = '/Applications/IINA.app/Contents/MacOS/iina-plugin';

test('the release build makes a versioned general-user archive with no build-machine path', {skip: !existsSync(iinaPack) && 'IINA is not installed'}, () => {
  const {version} = JSON.parse(readFileSync(join(root, 'plugin/Info.json'), 'utf8'));
  execFileSync(process.execPath, ['scripts/build-plugin.mjs', '--release'], {cwd: root, stdio: 'pipe'});
  const archive = join(root, 'dist', `Cue-${version}.iinaplgz`);
  assert.ok(existsSync(archive));
  const dir = mkdtempSync(join(tmpdir(), 'cue-release-'));
  try {
    execFileSync('/usr/bin/ditto', ['-xk', archive, dir]);
    assert.deepEqual(readdirSync(dir).sort(), ['Info.json', 'dist', 'preferences.html', 'sidebar.html']);
    for (const name of ['main.js', 'global.js']) {
      const text = readFileSync(join(dir, 'dist', name), 'utf8');
      for (const leak of [root, homedir(), '/Users/', 'scripts/cue-helper']) assert.ok(!text.includes(leak), `${name} contains ${leak}`);
    }
    assert.match(readFileSync(join(dir, 'dist/main.js'), 'utf8'), /devBootstrap: ""/);
    assert.match(readFileSync(join(dir, 'preferences.html'), 'utf8'), /id="dev-setup" hidden/);
    assert.equal(readFileSync(join(dir, 'Info.json'), 'utf8'), readFileSync(join(root, 'plugin/Info.json'), 'utf8'));
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
  // The development link loads plugin/dist; a release build must leave it alone.
  if (existsSync(join(root, 'plugin/dist/main.js'))) {
    assert.doesNotMatch(readFileSync(join(root, 'plugin/dist/main.js'), 'utf8'), /devBootstrap: ""/);
  }
});
