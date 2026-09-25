import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {modelErrorText, modelRows, modelsBusy, type ModelsStatus, type ModelStatus} from '../src/speech-models';
import {errorStatus} from '../src/control';

const GiB = 2 ** 30;
const model = (over: Partial<ModelStatus> & {id: string}): ModelStatus => ({
  bytes: 3_659_530_240, disk_bytes: 5_979_459_520, bytes_done: 0, state: 'missing', optional: true, min_ram_bytes: 16 * GiB,
  fits_memory: true, selected: false, ...over,
});
const status = (models: ModelStatus[], extra: Partial<ModelsStatus> = {}): ModelsStatus => ({
  selected: models.find((m) => m.selected)?.id ?? 'e2b', ram_bytes: 64 * GiB, models, download: null, trial: null, ...extra,
});
const e2b = model({id: 'e2b', bytes: 2_588_147_712, disk_bytes: 3_489_726_184, bytes_done: 2_588_147_712, state: 'installed', optional: false, selected: true});

test('the default model is in use and a larger one offers its download with size and memory', () => {
  const [first, second] = modelRows(status([e2b, model({id: 'e4b'})]));
  assert.equal(first.name, 'Gemma 4 E2B');
  assert.equal(first.checked, true);
  assert.equal(first.note, 'In use');
  assert.equal(first.facts, 'Installed with Cue · needs 16 GB of memory');
  assert.deepEqual(first.actions, []);
  assert.equal(second.name, 'Gemma 4 E4B');
  assert.equal(second.facts, '3.7 GB download · needs 6.0 GB of disk space and 16 GB of memory', 'disk counts the compile cache');
  assert.equal(second.disabled, true, 'a model that is not downloaded cannot be chosen yet');
  assert.deepEqual(second.actions, [{action: 'download', label: 'Download (3.7 GB)'}]);
});

test('a download shows progress and only Cancel, and nothing else can start meanwhile', () => {
  const rows = modelRows(status([e2b, model({id: 'e4b', state: 'partial', bytes_done: 1_829_765_120}), model({id: '12b', bytes: 6_883_278_368, min_ram_bytes: 24 * GiB})],
    {download: {model: 'e4b', phase: 'downloading'}}));
  assert.equal(rows[1].progress, 50);
  assert.equal(rows[1].bytes, '1.8 GB of 3.7 GB (50%)');
  assert.deepEqual(rows[1].actions.map((a) => a.action), ['cancel']);
  assert.equal(rows[1].note, 'Downloading…');
  assert.deepEqual(rows[2].actions, [], 'no second download while one runs');
  assert.equal(modelsBusy(status([e2b], {download: {model: 'e4b', phase: 'downloading'}})), true);
});

test('a stopped download offers to resume and says it stopped', () => {
  const [, row] = modelRows(status([e2b, model({id: 'e4b', state: 'partial', bytes_done: 1_000_000_000})],
    {download: {model: 'e4b', phase: 'error', error: {code: 'MODEL_DOWNLOAD_FAILED'}}}));
  assert.deepEqual(row.actions, [{action: 'download', label: 'Resume download (3.7 GB)'}]);
  assert.equal(row.noteTone, 'error');
  assert.match(row.note, /continue where it left off/);
});

test('an installed model can be chosen or removed; the trial is announced and then reported', () => {
  const installed = model({id: 'e4b', state: 'installed', bytes_done: 3_659_530_240});
  const [, idle] = modelRows(status([e2b, installed]));
  assert.equal(idle.facts, 'Downloaded · uses 6.0 GB of disk space · needs 16 GB of memory');
  assert.equal(idle.disabled, false);
  assert.deepEqual(idle.actions.map((a) => a.action), ['remove']);
  const [, trying] = modelRows(status([e2b, installed], {trial: {model: 'e4b', phase: 'smoking'}}));
  assert.equal(trying.note, 'Trying a short spoken clip…');
  assert.equal(trying.disabled, true);
  assert.equal(modelsBusy(status([e2b, installed], {trial: {model: 'e4b', phase: 'smoking'}})), true);
  const passed = modelRows(status([{...e2b, selected: false}, {...installed, selected: true}], {trial: {model: 'e4b', phase: 'passed', seconds: 6.1}}));
  assert.equal(passed[1].checked, true);
  assert.equal(passed[1].note, 'In use. The test clip took 6.1 s.');
  assert.deepEqual(passed[1].actions, [], 'the model in use cannot be removed');
  const [, failed] = modelRows(status([e2b, installed], {trial: {model: 'e4b', phase: 'failed', reason: 'no subtitles'}}));
  assert.equal(failed.noteTone, 'error');
  assert.match(failed.note, /kept the previous model/);
});

test('a Mac with too little memory sees why a model is unavailable', () => {
  const [, , big] = modelRows(status([e2b, model({id: 'e4b'}), model({id: '12b', bytes: 6_883_278_368, min_ram_bytes: 24 * GiB, fits_memory: false})]));
  assert.equal(big.disabled, true);
  assert.deepEqual(big.actions, []);
  assert.equal(big.note, 'Needs 24 GB of memory. This Mac has less.');
});

test('helper refusals read as plain sentences under the model', () => {
  const big = model({id: '12b', bytes: 6_883_278_368, disk_bytes: 6_883_278_368, min_ram_bytes: 24 * GiB});
  assert.equal(modelErrorText('SETUP_BUSY', big), 'Turn off AI subtitles in every IINA window, then choose the model.');
  assert.equal(modelErrorText('DISK_FULL', big), 'Not enough disk space. About 6.9 GB is needed.');
  assert.equal(modelErrorText('SOMETHING_ELSE', big), 'That did not work. Try again.');
  const [, row] = modelRows(status([e2b, big]), {model: '12b', code: 'SETUP_BUSY'});
  assert.equal(row.noteTone, 'error');
  assert.doesNotMatch(row.note, /SETUP_BUSY/);
});

test('a window that turns captions on during a model trial is told to retry shortly', () => {
  const status = errorStatus('MODEL_SWITCHING');
  assert.equal(status.title, 'Speech model changing');
  assert.equal(status.detail, 'Cue is trying the speech model chosen in Advanced. Retry in a moment.');
  assert.equal(status.retry, true);
});

test('no status means no speech model section', () => {
  assert.deepEqual(modelRows(null), []);
  assert.equal(modelsBusy(null), false);
});

test('the sidebar has the speech model group and sends the chosen action', () => {
  const html = readFileSync('plugin/sidebar.html', 'utf8');
  assert.match(html, /<fieldset id="speech-models"[^>]*hidden>/);
  assert.match(html, /iina\.onMessage\('cue-models'/);
  assert.match(html, /iina\.postMessage\('model',\{action:'use',model:row\.id\}\)/);
  assert.match(html, /iina\.postMessage\('model',\{action:a\.action,model:row\.id\}\)/);
  // The larger models are credited beside their downloads, and the links open through the plugin.
  const group = html.slice(html.indexOf('<fieldset id="speech-models"'), html.indexOf('</fieldset>'));
  assert.match(group, /data-link="gemma-e4b"[^>]*>Gemma 4 E4B \(Google, Apache 2\.0\)</);
  assert.match(group, /data-link="gemma-12b"[^>]*>Gemma 4 12B \(Google, Apache 2\.0\)</);
  assert.match(html, /querySelectorAll\('#setup-credits a\[data-link\],#speech-model-credits a\[data-link\]'\)/);
});
