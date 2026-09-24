import {execFileSync} from "node:child_process";
import {mkdtempSync, readdirSync, readFileSync, rmSync, statSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

const MACHO = new Set([0xfeedfacf, 0xcffaedfe, 0xfeedface, 0xcefaedfe, 0xcafebabe, 0xbebafeca]);

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const info = statSync(path);
    if (info.isDirectory()) { walk(path); continue; }
    if (name.endsWith(".dylib") || name.endsWith(".so")) throw new Error(`native library in plugin archive: ${name}`);
    const data = readFileSync(path);
    if (data.length >= 4 && (MACHO.has(data.readUInt32BE(0)) || MACHO.has(data.readUInt32LE(0)))) {
      throw new Error(`Mach-O in plugin archive: ${name}`);
    }
    if ((info.mode & 0o111) && data.subarray(0, 2).toString() === "#!") {
      throw new Error(`executable script in plugin archive: ${name}`);
    }
  }
}

export function assertSafePluginArchive(archive) {
  const dir = mkdtempSync(join(tmpdir(), "cue-plugin-"));
  try {
    execFileSync("/usr/bin/ditto", ["-xk", archive, dir]);
    walk(dir);
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
}
