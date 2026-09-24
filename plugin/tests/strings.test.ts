import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {en, has, sidebarStrings, t, useCatalog} from '../src/strings';

const html = readFileSync('plugin/sidebar.html', 'utf8');
const decode = (text: string) => text.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');

test('every sidebar data-i18n key exists and its English fallback matches the catalog', () => {
  const tagged = [...html.matchAll(/data-i18n="([^"]+)"[^>]*>([^<]*)</g)];
  assert.ok(tagged.length > 30);
  for (const [, key, text] of tagged) {
    assert.ok(has(key), `unknown key ${key}`);
    assert.equal(decode(text), en[key as keyof typeof en], key);
  }
  for (const element of html.matchAll(/<[^>]*data-i18n-attr="([^"]+)"[^>]*>/g)) {
    for (const pair of element[1].split(';')) {
      const [attr, key] = pair.split(':');
      assert.ok(has(key), `unknown key ${key}`);
      assert.match(element[0], new RegExp(`${attr}="${en[key as keyof typeof en].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`), key);
    }
  }
});

test('sidebar script defaults match the catalog', () => {
  const defaults = html.match(/let strings=(\{.*\});\n/)?.[1];
  assert.ok(defaults);
  for (const [, key, value] of defaults.matchAll(/'([^']+)':'([^']*)'/g)) assert.equal(value, en[key as keyof typeof en], key);
});

test('messages are whole sentences with named placeholders', () => {
  assert.equal(t('status.readyDetail', {seconds: 48}), 'Loaded in the player for the next 48 s.');
  assert.equal(t('remux.saved', {path: '/tmp/a {b}.mkv'}), 'MKV copy saved: /tmp/a {b}.mkv');
  assert.equal(t('menu.output', {}), 'Output: {label}');
  for (const [key, value] of Object.entries(en)) {
    assert.doesNotMatch(value, /\{\s*\}/, key);
    assert.equal(value, value.trim(), `${key} has leading or trailing space and is likely a fragment`);
  }
});

test('a partial catalog falls back to English and only sidebar keys reach the page', () => {
  useCatalog({'status.ready': '字幕已就緒'});
  try {
    assert.equal(t('status.ready'), '字幕已就緒');
    assert.equal(t('status.starting'), 'Starting');
  } finally { useCatalog({}); }
  const sent = Object.keys(sidebarStrings());
  assert.ok(sent.length && sent.every(key => key.startsWith('sidebar.') || key.startsWith('lang.')));
});

test('plugin code keeps user-facing English in the catalog', () => {
  for (const file of ['plugin/src/main.ts', 'plugin/src/control.ts', 'plugin/src/player.ts']) {
    const source = readFileSync(file, 'utf8');
    // A capitalised multi-word literal is almost always UI copy.
    const literals = [...source.matchAll(/["`]([A-Z][a-z]+(?: [a-z'’]+){2,}[^"`]*)["`]/g)].map(match => match[1]);
    assert.deepEqual(literals, [], file);
  }
});
