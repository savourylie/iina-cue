import {test} from 'node:test';
import assert from 'node:assert/strict';
import {INSTALLED_SUPPORT} from '../src/launch';

test('the plugin knows an installed helper\'s version, and stops it only after releasing its own lease', async () => {
  const launcher = `${INSTALLED_SUPPORT}/runtime/bin/cue-helper`;
  const connection = {host: '127.0.0.1', port: 12345, token: 'a'.repeat(64), protocol_version: 1, instance_id: 'helper-one', helper_version: '0.1.6'};
  const requests: string[] = [];
  let boots = 0;
  let refuse = true;
  let exited = false;
  (globalThis as any).CUE_BOOTSTRAP_DEFAULT = '/project/cue-helper';
  const answer = (method: string, url: string, options: any) => {
    const path = new URL(url).pathname;
    requests.push(`${method} ${path} client=${options.headers['X-Cue-Client'] ?? '-'}`);
    if (exited) throw new Error('connection refused');
    if (path === '/v1/clients') return {data: {instance_id: 'helper-one', client_id: `client-${boots}`}};
    if (path === '/v1/shutdown') {
      if (refuse) return {data: {instance_id: 'helper-one', error: {code: 'CLIENTS_ACTIVE'}}};
      return {data: {instance_id: 'helper-one', stopping: true}};
    }
    if (path === '/v1/health') { exited = true; return {data: {instance_id: 'helper-one', helper_version: '0.1.6'}}; }
    return {data: {instance_id: 'helper-one', files_ready: true}};
  };
  (globalThis as any).iina = {
    preferences: {get: () => ''},
    file: {exists: (path: string) => path === `${INSTALLED_SUPPORT}/installed` || path === launcher},
    utils: {
      resolvePath: (path: string) => path.replace(/^~/, '/Users/cue'),
      exec: async () => { boots++; exited = false; return {status: 0, stdout: JSON.stringify(connection), stderr: ''}; },
    },
    http: {
      get: async (url: string, options: any) => answer('GET', url, options),
      post: async (url: string, options: any) => answer('POST', url, options),
      delete: async (url: string, options: any) => answer('DELETE', url, options),
    },
  };
  const {rpc, helperIdentity, stopHelper} = await import('../src/client');
  assert.equal(helperIdentity(), null, 'unknown before the first request');
  await rpc('GET', '/setup');
  assert.deepEqual(helperIdentity(), {version: '0.1.6', installed: true});

  // Another window holds a lease: the helper refuses, and nothing is stopped.
  requests.length = 0;
  assert.deepEqual(await stopHelper(async () => {}), {ok: false, code: 'CLIENTS_ACTIVE'});
  assert.deepEqual(requests, ['DELETE /v1/client client=client-1', 'POST /v1/shutdown client=-']);

  refuse = false;
  requests.length = 0;
  assert.deepEqual(await stopHelper(async () => {}), {ok: true});
  // It reconnects (the refusal dropped the connection), releases the new lease, then waits for the exit.
  assert.equal(boots, 2);
  assert.deepEqual(requests, [
    'POST /v1/clients client=-', 'DELETE /v1/client client=client-2', 'POST /v1/shutdown client=-',
    'GET /v1/health client=-', 'GET /v1/health client=-',
  ]);
  assert.equal(helperIdentity(), null);
  // The next request starts whatever runtime is installed now.
  await rpc('GET', '/setup');
  assert.equal(boots, 3);
});

test('a helper that cannot be started has nothing to stop', async () => {
  (globalThis as any).iina = {
    preferences: {get: () => ''},
    file: {exists: () => false},
    utils: {resolvePath: () => null, exec: async () => { throw new Error('must not run'); }},
    http: {},
  };
  const {disposeClient, stopHelper} = await import('../src/client');
  disposeClient(); // the module still holds the first test's connection
  assert.deepEqual(await stopHelper(async () => {}), {ok: true});
});
