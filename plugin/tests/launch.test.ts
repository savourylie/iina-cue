import {test} from 'node:test';
import assert from 'node:assert/strict';
import {INSTALLED_SUPPORT, planLaunch} from '../src/launch';

const dev = '/project/cue-helper';
const marker = `${INSTALLED_SUPPORT}/installed`;
const launcher = `${INSTALLED_SUPPORT}/runtime/bin/cue-helper`;
const python = `${INSTALLED_SUPPORT}/runtime/python/bin/python3.12`;
const absoluteLauncher = '/Users/dev/Library/Application Support/Cue/runtime/bin/cue-helper';
const absolutePython = '/Users/dev/Library/Application Support/Cue/runtime/python/bin/python3.12';

function exists(paths: string[]) {
  return (path: string) => paths.includes(path);
}

function resolve(path: string): string | null {
  if (path === launcher) return absoluteLauncher;
  if (path === python) return absolutePython;
  return null;
}

test('an explicit launcher preference is used as-is', () => {
  const plan = planLaunch({preference: '/custom/helper', devBootstrap: dev, exists: exists(['/custom/helper', marker, launcher]), resolve});
  assert.deepEqual(plan, {file: '/custom/helper', args: ['ensure']});
});

test('a missing explicit launcher reports setup required', () => {
  assert.throws(() => planLaunch({preference: '/missing/helper', devBootstrap: dev, exists: exists([dev]), resolve}), /SETUP_REQUIRED/);
});

test('development mode keeps the baked helper when Cue is not installed', () => {
  const plan = planLaunch({preference: '', devBootstrap: dev, exists: exists([dev]), resolve});
  assert.deepEqual(plan, {file: dev, args: ['ensure']});
});

test('a missing development helper reports setup required', () => {
  assert.throws(() => planLaunch({preference: ' ', devBootstrap: dev, exists: exists([]), resolve}), /SETUP_REQUIRED/);
});

test('installed mode runs the runtime launcher through /bin/sh', () => {
  const plan = planLaunch({preference: '', devBootstrap: dev, exists: exists([marker, launcher, python, dev]), resolve});
  assert.deepEqual(plan, {file: '/bin/sh', args: [absoluteLauncher, 'ensure']});
  assert.equal(plan.args[0].includes('/project/'), false);
});

test('installed mode runs the runtime Python when the launcher script is absent', () => {
  const plan = planLaunch({preference: '', devBootstrap: dev, exists: exists([marker, python, dev]), resolve});
  assert.deepEqual(plan, {file: absolutePython, args: ['-m', 'cue.cli', 'ensure']});
});

test('a marker without a runtime reports setup required and does not use the checkout helper', () => {
  assert.throws(() => planLaunch({preference: '', devBootstrap: dev, exists: exists([marker, dev]), resolve}), /SETUP_REQUIRED/);
});

test('without resolvePath the runtime script is still the program IINA expands', () => {
  const plan = planLaunch({preference: '', devBootstrap: dev, exists: exists([marker, launcher]), resolve: () => null});
  assert.deepEqual(plan, {file: launcher, args: ['ensure']});
});
