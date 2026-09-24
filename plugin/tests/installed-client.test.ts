import {test} from 'node:test';
import assert from 'node:assert/strict';
import {INSTALLED_SUPPORT} from '../src/launch';

test('the plugin starts an installed runtime through /bin/sh and ignores the baked checkout path', async () => {
  const launcher = `${INSTALLED_SUPPORT}/runtime/bin/cue-helper`;
  const absolute = '/Users/dev/Library/Application Support/Cue/runtime/bin/cue-helper';
  const connection = {host: '127.0.0.1', port: 12345, token: 'a'.repeat(64), protocol_version: 1, instance_id: 'helper-one'};
  const calls: [string, string[]][] = [];
  (globalThis as any).CUE_BOOTSTRAP_DEFAULT = '/project/cue-helper';
  const utils = {
    resolvePath(path: string) {
      if (this !== utils) throw new TypeError("self type check failed for Objective-C instance method");
      return path === launcher ? absolute : null;
    },
    exec: async (file: string, args: string[]) => {
      calls.push([file, args]);
      return {status: 0, stdout: JSON.stringify(connection), stderr: ''};
    },
  };
  (globalThis as any).iina = {
    preferences: {get: () => ''},
    file: {exists: (path: string) => path === `${INSTALLED_SUPPORT}/installed` || path === launcher || path === '/project/cue-helper'},
    utils,
    http: {
      post: async (url: string) => {
        if (url.endsWith('/clients')) return {data: {instance_id: 'helper-one', client_id: 'client-one'}};
        return {data: {instance_id: 'helper-one', session_id: 'session'}};
      },
      get: async () => ({data: {instance_id: 'helper-one'}}),
      delete: async () => ({data: {instance_id: 'helper-one'}}),
    },
  };
  const {rpc} = await import('../src/client');
  const snapshot = await rpc<any>('POST', '/sessions', {request_id: 'request'});
  assert.equal(snapshot.session_id, 'session');
  assert.deepEqual(calls, [['/bin/sh', [absolute, 'ensure']]]);
});
