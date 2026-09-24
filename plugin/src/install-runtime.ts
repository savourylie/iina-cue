import {createHash} from "node:crypto";
import {execFile} from "node:child_process";
import {mkdir, readFile, rename, rm, stat} from "node:fs/promises";
import {dirname, join} from "node:path";
import {promisify} from "node:util";

const exec = promisify(execFile);
export const DEFAULT_RAM_BYTES = 16 * 1024 * 1024 * 1024;

export interface PreflightFacts {
  arch: string;
  macos: string;
  iina: string;
  freeBytes: number;
  ramBytes: number;
  minimumMacos: string;
  bytesNeeded: number;
  ramThresholdBytes?: number;
}

export type Preflight =
  | {ok: true}
  | {ok: false; code: "UNSUPPORTED_MAC" | "MACOS_TOO_OLD" | "IINA_TOO_OLD" | "DISK_FULL" | "LOW_MEMORY"; reason: string};

function compareVersions(left: string, right: string): number {
  const a = left.split(".").map(Number);
  const b = right.split(".").map(Number);
  const count = Math.max(a.length, b.length);
  for (let i = 0; i < count; i++) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff < 0 ? -1 : 1;
  }
  return 0;
}

/** Refuse a Mac that cannot run the published runtime. No download starts here. */
export function preflight(facts: PreflightFacts): Preflight {
  if (facts.arch !== "arm64") return {ok: false, code: "UNSUPPORTED_MAC", reason: "Cue needs an Apple Silicon Mac."};
  if (compareVersions(facts.macos, facts.minimumMacos) < 0) {
    return {ok: false, code: "MACOS_TOO_OLD", reason: `macOS ${facts.minimumMacos} or later is required.`};
  }
  if (compareVersions(facts.iina, "1.4.0") < 0) return {ok: false, code: "IINA_TOO_OLD", reason: "IINA 1.4 or later is required."};
  if (facts.freeBytes < facts.bytesNeeded) {
    return {ok: false, code: "DISK_FULL", reason: `Not enough disk space. ${facts.bytesNeeded} bytes are required.`};
  }
  const ram = facts.ramThresholdBytes ?? DEFAULT_RAM_BYTES;
  if (facts.ramBytes < ram) return {ok: false, code: "LOW_MEMORY", reason: `At least ${ram} bytes of memory are required.`};
  return {ok: true};
}

export function maySwap(state: {remuxActive: boolean; sessions: number}): {ok: true} | {ok: false; code: "HELPER_RESTART_REQUIRED"} {
  if (state.remuxActive || state.sessions > 0) return {ok: false, code: "HELPER_RESTART_REQUIRED"};
  return {ok: true};
}

/** Resume with curl. The program is /usr/bin/curl, never a file inside the plugin. */
export function curlResumeArgs(url: string, destination: string): string[] {
  return ["/usr/bin/curl", "-L", "--fail", "-C", "-", "-o", destination, url];
}

export function startInstall(userStarted: boolean): void {
  if (!userStarted) throw new Error("SETUP_NOT_STARTED");
}

export async function sha256File(path: string): Promise<string> {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

/**
 * Verify the archive and unpack it beside `destination`, then rename it into
 * place. A bad hash or a failed unpack leaves an existing runtime untouched.
 * A busy helper refuses the swap.
 */
export async function installVerifiedArchive(options: {
  archive: string;
  expectedSha256: string;
  destination: string;
  remuxActive?: boolean;
  sessions?: number;
}): Promise<{ok: true} | {ok: false; code: "SHA256_MISMATCH" | "HELPER_RESTART_REQUIRED" | "UNPACK_FAILED"; reason: string}> {
  const decision = maySwap({remuxActive: options.remuxActive ?? false, sessions: options.sessions ?? 0});
  if (!decision.ok) return {ok: false, code: decision.code, reason: "Wait for the MKV copy to finish or close other Cue windows, then retry."};
  const actual = await sha256File(options.archive);
  if (actual !== options.expectedSha256) {
    return {ok: false, code: "SHA256_MISMATCH", reason: "The runtime download does not match the published checksum."};
  }
  const incoming = `${options.destination}.incoming`;
  await rm(incoming, {recursive: true, force: true});
  await mkdir(incoming, {recursive: true});
  const flags = options.archive.endsWith(".tar.xz") || options.archive.endsWith(".txz") ? ["-xJf"] : ["-xf"];
  try {
    await exec("/usr/bin/tar", [...flags, options.archive, "-C", incoming]);
  } catch {
    await rm(incoming, {recursive: true, force: true});
    return {ok: false, code: "UNPACK_FAILED", reason: "The runtime archive could not be unpacked."};
  }
  const previous = `${options.destination}.previous`;
  await rm(previous, {recursive: true, force: true});
  try {
    if (await exists(options.destination)) await rename(options.destination, previous);
    await rename(incoming, options.destination);
    await rm(previous, {recursive: true, force: true});
  } catch {
    if (await exists(previous) && !(await exists(options.destination))) await rename(previous, options.destination);
    await rm(incoming, {recursive: true, force: true});
    return {ok: false, code: "UNPACK_FAILED", reason: "The runtime archive could not be unpacked."};
  }
  return {ok: true};
}

async function exists(path: string): Promise<boolean> {
  try { await stat(path); return true; } catch { return false; }
}

export function runtimeParent(destination: string): string {
  return dirname(join(destination, "marker"));
}
