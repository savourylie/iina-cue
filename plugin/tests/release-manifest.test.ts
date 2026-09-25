import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {RUNTIME_ARCHIVE_BYTES, RUNTIME_ARCHIVE_SHA256, RUNTIME_ARCHIVE_URL} from '../src/runtime-install';

const root = resolve(import.meta.dirname, '../..');
const manifest = JSON.parse(readFileSync(resolve(root, 'release/runtime-0.1.5.json'), 'utf8'));
const info = JSON.parse(readFileSync(resolve(root, 'plugin/Info.json'), 'utf8'));

test('the runtime manifest records this notarized archive, including macOS 27.0', () => {
  assert.equal(manifest.version, '0.1.5');
  assert.equal(manifest.size, 270969508);
  assert.equal(manifest.sha256, '70218fd01793d234d280401420aab1dfaf0ba874098a17a9479e3ffbaa91197f');
  assert.equal(manifest.minimum_macos, '27.0');
  assert.equal(manifest.architecture, 'arm64');
  assert.deepEqual(manifest.compatible_plugin_versions, ['0.1.0']);
  assert.equal(manifest.published, true);
  assert.equal(RUNTIME_ARCHIVE_URL, manifest.url);
  assert.equal(RUNTIME_ARCHIVE_SHA256, manifest.sha256);
  assert.equal(RUNTIME_ARCHIVE_BYTES, manifest.size);
  const url = new URL(manifest.url);
  assert.equal(url.protocol, 'https:');
  assert.equal(url.hostname, 'github.com');
});

test('allowed domains are loopback plus the release hosts and nothing else', () => {
  assert.deepEqual(info.allowedDomains, [
    '127.0.0.1',
    'github.com',
    'release-assets.githubusercontent.com',
    'objects.githubusercontent.com',
  ]);
});
