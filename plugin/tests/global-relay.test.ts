import {test} from 'node:test';
import assert from 'node:assert/strict';
import {relayRuntimeUpdates} from '../src/global';

test('the global instance relays an update to every window that said hello, by label', () => {
  const listeners = new Map<string, (data: any, sender: string) => void>();
  const sent: [string, string, unknown][] = [];
  relayRuntimeUpdates({
    onMessage: (name, callback) => { listeners.set(name, callback); },
    postMessage: (target, name, data) => { sent.push([target, name, data]); },
  });
  listeners.get('cue-hello')!({}, 'player-1');
  listeners.get('cue-hello')!({}, 'player-2');
  // A window that never said hello (opened before this instance) is learned from its own message.
  listeners.get('cue-update')!({phase: 'stop', origin: 'w3'}, 'player-3');
  assert.deepEqual(sent.map(([target]) => target).sort(), ['player-1', 'player-2', 'player-3']);
  assert.ok(sent.every(([, name, data]) => name === 'cue-update' && (data as {phase: string}).phase === 'stop'));
  sent.length = 0;
  listeners.get('cue-update')!({phase: 'resume', origin: 'w3'}, 'player-3');
  assert.equal(sent.length, 3);
});
