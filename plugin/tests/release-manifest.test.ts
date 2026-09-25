import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {RUNTIME_ARCHIVE_BYTES, RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URLS, RUNTIME_MINIMUM_MACOS} from '../src/runtime-install';

const root = resolve(import.meta.dirname, '../..');
const manifest = JSON.parse(readFileSync(resolve(root, 'release/runtime-0.1.6.json'), 'utf8'));
const info = JSON.parse(readFileSync(resolve(root, 'plugin/Info.json'), 'utf8'));

test('the runtime manifest records the notarized macOS 14.0 archive and the plugin pins it', () => {
  assert.equal(manifest.version, '0.1.6');
  assert.equal(manifest.size, 267837724);
  assert.equal(manifest.sha256, '4dea7f196f67dbcc34872bdb02eb2cfac54378c3e98da72754240f76f6186483');
  assert.equal(manifest.minimum_macos, '14.0');
  assert.equal(manifest.architecture, 'arm64');
  assert.deepEqual(manifest.compatible_plugin_versions, ['0.1.0']);
  assert.equal(manifest.published, true);
  assert.deepEqual([...RUNTIME_ARCHIVE_URLS], manifest.urls);
  assert.equal(RUNTIME_ARCHIVE_SHA256, manifest.sha256);
  assert.equal(RUNTIME_ARCHIVE_BYTES, manifest.size);
  assert.equal(RUNTIME_MINIMUM_MACOS, manifest.minimum_macos);
});

test('every runtime URL is HTTPS, and the Hugging Face copy is pinned to a commit', () => {
  const [primary, backup] = manifest.urls.map((url: string) => new URL(url));
  for (const url of [primary, backup]) assert.equal(url.protocol, 'https:');
  assert.equal(primary.hostname, 'huggingface.co');
  assert.match(primary.pathname, /^\/onionmonster\/cue-runtime\/resolve\/[0-9a-f]{40}\/runtime-0\.1\.6\.tar\.xz$/);
  assert.equal(backup.hostname, 'github.com');
  assert.match(backup.pathname, /\/releases\/download\/runtime-0\.1\.6\/runtime-0\.1\.6\.tar\.xz$/);
});

test('allowed domains are loopback plus the two runtime hosts and nothing else', () => {
  assert.deepEqual(info.allowedDomains, [
    '127.0.0.1',
    'github.com',
    'release-assets.githubusercontent.com',
    'objects.githubusercontent.com',
    'huggingface.co',
    '*.hf.co',
  ]);
});
