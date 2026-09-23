import {build} from 'esbuild';
import {mkdir,copyFile,rm,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
const root=resolve('.');
await mkdir('plugin/dist',{recursive:true});
await build({entryPoints:['plugin/src/main.ts','plugin/src/global.ts'],outdir:'plugin/dist',bundle:true,format:'iife',platform:'neutral',target:'safari14',define:{CUE_BOOTSTRAP_DEFAULT:JSON.stringify(resolve('scripts/cue-helper'))}});
const staging='dist/Cue.iinaplugin';
await rm(staging,{recursive:true,force:true});
await mkdir(staging+'/dist',{recursive:true});
for(const name of ['Info.json','preferences.html','sidebar.html']) await copyFile('plugin/'+name,staging+'/'+name);
for(const name of ['main.js','global.js']) await copyFile('plugin/dist/'+name,staging+'/dist/'+name);
// Official IINA pack command keeps the archive layout compatible with installer.
await rm('dist/Cue.iinaplugin-0.1.0.iinaplgz',{force:true});
execFileSync('/Applications/IINA.app/Contents/MacOS/iina-plugin',['pack','Cue.iinaplugin'],{cwd:resolve('dist'),stdio:'inherit'});
console.log('Built local development preview. Helper remains in '+root);
