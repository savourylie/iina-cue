export const DEFAULT_RAM_BYTES = 16 * 1024 * 1024 * 1024;

/** A fact the plugin could not read is left out; preflight does not guess it. */
export interface PreflightFacts {
  arch?: string;
  macos?: string;
  iina: string;
  freeBytes?: number;
  ramBytes?: number;
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
  if (facts.arch !== undefined && facts.arch !== "arm64") return {ok: false, code: "UNSUPPORTED_MAC", reason: "Cue needs an Apple Silicon Mac."};
  if (facts.macos !== undefined && compareVersions(facts.macos, facts.minimumMacos) < 0) {
    return {ok: false, code: "MACOS_TOO_OLD", reason: `macOS ${facts.minimumMacos} or later is required.`};
  }
  if (compareVersions(facts.iina, "1.4.0") < 0) return {ok: false, code: "IINA_TOO_OLD", reason: "IINA 1.4 or later is required."};
  if (facts.freeBytes !== undefined && facts.freeBytes < facts.bytesNeeded) {
    return {ok: false, code: "DISK_FULL", reason: `Not enough disk space. ${facts.bytesNeeded} bytes are required.`};
  }
  const ram = facts.ramThresholdBytes ?? DEFAULT_RAM_BYTES;
  if (facts.ramBytes !== undefined && facts.ramBytes < ram) return {ok: false, code: "LOW_MEMORY", reason: `At least ${ram} bytes of memory are required.`};
  return {ok: true};
}

export function maySwap(state: {remuxActive: boolean; sessions: number}): {ok: true} | {ok: false; code: "HELPER_RESTART_REQUIRED"} {
  if (state.remuxActive || state.sessions > 0) return {ok: false, code: "HELPER_RESTART_REQUIRED"};
  return {ok: true};
}

/** Resume with curl. The program is /usr/bin/curl, never a file inside the plugin. */
export function curlResumeArgs(url: string, destination: string): string[] {
  // A stalled host (under 1 KB/s for 60 s) fails, so the next copy can take over.
  return ["/usr/bin/curl", "-L", "--fail", "--speed-limit", "1024", "--speed-time", "60", "-C", "-", "-o", destination, url];
}

export function startInstall(userStarted: boolean): void {
  if (!userStarted) throw new Error("SETUP_NOT_STARTED");
}
