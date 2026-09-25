// Build the Cue plugin archive.
//   node scripts/build-plugin.mjs            development pack for this checkout
//   node scripts/build-plugin.mjs --release  general-user pack
// The development pack bakes in this checkout's helper launcher and shows the
// Terminal steps. The general-user pack does neither: it starts only the
// runtime installed in ~/Library/Application Support/Cue, or shows setup.
import {build} from 'esbuild';
import {mkdir,copyFile,readFile,rename,rm,writeFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {assertSafePluginArchive} from './check-plugin-archive.mjs';
import {preferencesForPack} from './preferences-pack.mjs';

const release = process.argv.includes('--release');
const root = resolve('.');
const {version} = JSON.parse(await readFile('plugin/Info.json', 'utf8'));
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error(`plugin/Info.json version is not x.y.z: ${version}`);

// The development link loads plugin/dist, so only the development build writes there.
const bundle = release ? 'dist/release/bundle' : 'plugin/dist';
const work = release ? 'dist/release' : 'dist';
const archive = release ? `dist/Cue-${version}.iinaplgz` : `dist/Cue-${version}-dev.iinaplgz`;

await rm(bundle, {recursive: true, force: true});
await mkdir(bundle, {recursive: true});
await build({
  entryPoints: ['plugin/src/main.ts', 'plugin/src/global.ts'],
  outdir: bundle, bundle: true, format: 'iife', platform: 'neutral', target: 'safari14',
  // An empty launcher is never absolute, so planLaunch falls through to setup.
  define: {CUE_BOOTSTRAP_DEFAULT: JSON.stringify(release ? '' : resolve('scripts/cue-helper'))},
});

if (release) {
  for (const name of ['main.js', 'global.js']) {
    const text = await readFile(`${bundle}/${name}`, 'utf8');
    for (const leak of [root, homedir(), '/Users/', 'scripts/cue-helper']) {
      if (text.includes(leak)) throw new Error(`general-user bundle ${name} contains a build-machine path: ${leak}`);
    }
  }
}

const staging = `${work}/Cue.iinaplugin`;
await rm(staging, {recursive: true, force: true});
await mkdir(`${staging}/dist`, {recursive: true});
for (const name of ['Info.json', 'sidebar.html']) await copyFile(`plugin/${name}`, `${staging}/${name}`);
await writeFile(`${staging}/preferences.html`, preferencesForPack(await readFile('plugin/preferences.html', 'utf8'), !release));
for (const name of ['main.js', 'global.js']) await copyFile(`${bundle}/${name}`, `${staging}/dist/${name}`);

// IINA's official pack command keeps the archive layout its installer expects.
// It names the result after the folder and version; rename it afterwards.
const packed = `${work}/Cue.iinaplugin-${version}.iinaplgz`;
await rm(packed, {force: true});
await rm(archive, {force: true});
execFileSync('/Applications/IINA.app/Contents/MacOS/iina-plugin', ['pack', 'Cue.iinaplugin'], {cwd: resolve(work), stdio: 'inherit'});
await rename(packed, archive);
assertSafePluginArchive(resolve(archive));

if (release) console.log(`Built general-user pack: ${resolve(archive)}`);
else console.log(`Built development pack: ${resolve(archive)}. Helper remains in ${root}`);
