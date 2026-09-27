import {curlResumeArgs, maySwap} from "./install-runtime";
import {INSTALLED_SUPPORT} from "./launch";
import {t} from "./strings";

/**
 * Hugging Face first, pinned to a commit; the GitHub Release is the same file.
 * GitHub's release CDN measured about 125 KB/s here against 7.5 MB/s from
 * Hugging Face. Both copies are byte-identical, so curl -C - may resume a
 * partial file from either one. The SHA-256 decides, not the host.
 */
export const RUNTIME_ARCHIVE_URLS = [
  "https://huggingface.co/onionmonster/cue-runtime/resolve/dcf288cca59483d3b562af9ad04403384c327e56/runtime-0.1.9.tar.xz",
  "https://github.com/savourylie/iina-cue/releases/download/runtime-0.1.9/runtime-0.1.9.tar.xz",
] as const;
export const RUNTIME_ARCHIVE_SHA256 = "8f4d4dda2358d767fcb84a4739c6533195cd9aaa80d6756735a531e43a33a68e";
export const RUNTIME_ARCHIVE_BYTES = 283954324;
/** The runtime this plugin installs. An installed helper that reports an older version is offered an update. */
export const RUNTIME_VERSION = "0.1.9";
/** Named for its version: another version's partial download must never be resumed into this one. */
export const RUNTIME_PARTIAL = `runtime-${RUNTIME_VERSION}.tar.xz.partial`;

/** Remove downloads of other runtime versions, including the unversioned name older plugins used. */
export const CLEAR_STALE_PARTIALS_SCRIPT = `
PATH=/usr/bin:/bin
export PATH
for f in "$1"/runtime.tar.xz.partial "$1"/runtime-*.tar.xz.partial; do
  if [ "$f" != "$2" ]; then rm -f "$f"; fi
done
`;

/**
 * IINA's utils.exec keeps only LC_ALL, so the script sets PATH itself.
 * The published archive's top directory is the version name. Flatten it so
 * bin/ lands on Cue/runtime, then write the installed marker beside it.
 * A name ending in .partial is still an xz archive; tar detects that.
 */
export const UNPACK_RUNTIME_SCRIPT = `
PATH=/usr/bin:/bin
export PATH
set -eu
archive=$1
destination=$2
expected=$3
actual=$(shasum -a 256 "$archive" | awk 'NR==1 { print $1 }')
if [ "$actual" != "$expected" ]; then
  printf '%s\\n' SHA256_MISMATCH >&2
  exit 2
fi
incoming="\${destination}.incoming"
previous="\${destination}.previous"
rm -rf "$incoming"
mkdir -p "$incoming"
if ! tar -xf "$archive" -C "$incoming"; then
  rm -rf "$incoming"
  printf '%s\\n' UNPACK_FAILED >&2
  exit 3
fi
if [ ! -d "$incoming/bin" ]; then
  count=0
  only=""
  for entry in "$incoming"/*; do
    if [ ! -e "$entry" ]; then
      continue
    fi
    count=$((count + 1))
    only=$entry
  done
  if [ "$count" -eq 1 ] && [ -d "$only/bin" ]; then
    find "$only" -mindepth 1 -maxdepth 1 -exec mv {} "$incoming/" \\;
    rm -rf "$only"
  fi
fi
if [ ! -d "$incoming/bin" ]; then
  rm -rf "$incoming"
  printf '%s\\n' UNPACK_FAILED >&2
  exit 3
fi
rm -rf "$previous"
if [ -e "$destination" ]; then
  mv "$destination" "$previous"
fi
if ! mv "$incoming" "$destination"; then
  if [ ! -e "$destination" ] && [ -e "$previous" ]; then
    mv "$previous" "$destination"
  fi
  rm -rf "$incoming"
  printf '%s\\n' UNPACK_FAILED >&2
  exit 3
fi
marker="$(dirname "$destination")/installed"
printf '1\\n' > "$marker"
rm -rf "$previous"
# The runtime is in place; the 268 MB archive is no longer needed.
rm -f "$archive"
`;

export function unpackRuntimeInvocation(archive: string, destination: string, expectedSha256: string): {file: string; args: string[]} {
  return {file: "/bin/sh", args: ["-c", UNPACK_RUNTIME_SCRIPT, "cue-unpack", archive, destination, expectedSha256]};
}

export interface RuntimeExecResult {
  status: number;
  stdout?: string;
  stderr?: string;
}

/** Download the published runtime, check it, and unpack it into Cue's folder. */
export async function installPublishedRuntime(deps: {
  resolve: (path: string) => string | null | undefined;
  exec: (file: string, args: string[]) => Promise<RuntimeExecResult>;
  remuxActive: boolean;
  sessions: number;
  /** Bytes of the archive on disk so far, about once a second while curl runs. */
  onProgress?: (done: number, total: number) => void;
  /**
   * A file's size without starting a process. IINA waits for each exec in turn, so a
   * size check through exec would only answer after curl has finished.
   */
  fileSize?: (path: string) => number | null;
  /** The download is complete; checking and unpacking take tens of seconds. */
  onUnpack?: () => void;
  wait?: (ms: number) => Promise<void>;
  /**
   * Replacing an installed runtime: runs after the download has passed its checksum
   * and before anything is swapped. It stops the old helper, or refuses with a reason.
   */
  beforeSwap?: () => Promise<{ok: true} | {ok: false; reason: string}>;
  /** What a busy helper is told; setup and an update phrase it differently. */
  busyReason?: string;
}): Promise<{ok: true} | {ok: false; reason: string}> {
  const decision = maySwap({remuxActive: deps.remuxActive, sessions: deps.sessions});
  if (!decision.ok) return {ok: false, reason: deps.busyReason ?? t("sidebar.setupRestart")};
  const support = deps.resolve(INSTALLED_SUPPORT);
  if (!support || !support.startsWith("/")) return {ok: false, reason: t("sidebar.setupNoFolder")};
  const partial = `${support}/${RUNTIME_PARTIAL}`;
  await deps.exec("/bin/sh", ["-c", CLEAR_STALE_PARTIALS_SCRIPT, "cue-clear", support, partial]).catch(() => undefined);
  const size = async () => deps.fileSize ? deps.fileSize(partial) ?? 0
    : Number((await deps.exec("/usr/bin/stat", ["-f%z", partial]).catch(() => ({stdout: ""}))).stdout);
  // A download that finished before a refused swap is not fetched again; the checksum still decides.
  let downloaded = await size() === RUNTIME_ARCHIVE_BYTES;
  for (const url of downloaded ? [] : RUNTIME_ARCHIVE_URLS) {
    const curl = curlResumeArgs(url, partial);
    let running = true;
    const download = deps.exec(curl[0], curl.slice(1)).finally(() => { running = false; });
    // curl through utils.exec reports nothing until it exits; read the file size instead.
    // Not awaited: installing never waits on the progress reader.
    void (async () => {
      const {onProgress, wait} = deps;
      if (!onProgress || !wait) return;
      while (running) {
        const bytes = await size();
        if (running && Number.isFinite(bytes) && bytes > 0) onProgress(bytes, RUNTIME_ARCHIVE_BYTES);
        await wait(1000);
      }
    })();
    const result = await download;
    if (result.status === 0) { downloaded = true; break; }
  }
  if (!downloaded) return {ok: false, reason: t("sidebar.setupDownloadStopped")};
  deps.onUnpack?.();
  // Resuming a bad file would fail the same way on every retry. Start over.
  const discard = async () => { await deps.exec("/bin/rm", ["-f", partial]); return {ok: false as const, reason: t("sidebar.setupChecksum")}; };
  if (deps.beforeSwap) {
    // Check the download first: a bad file never costs a working helper its run.
    const sum = await deps.exec("/usr/bin/shasum", ["-a", "256", partial]).catch(() => ({status: 1, stdout: ""}));
    if ((sum.stdout ?? "").trim().split(/\s+/)[0] !== RUNTIME_ARCHIVE_SHA256) return discard();
    const ready = await deps.beforeSwap();
    // The verified download stays for the next attempt.
    if (!ready.ok) return ready;
  }
  const unpack = unpackRuntimeInvocation(partial, `${support}/runtime`, RUNTIME_ARCHIVE_SHA256);
  const unpacked = await deps.exec(unpack.file, unpack.args);
  if (unpacked.status === 2) return discard();
  if (unpacked.status !== 0) return {ok: false, reason: t("sidebar.setupUnpackFailed")};
  return {ok: true};
}

/** Must match release/runtime-0.1.9.json and models/manifest.json. */
export const RUNTIME_MINIMUM_MACOS = "14.0";
export const MODEL_BYTES = 3564002544;

/**
 * Read this Mac with system tools. A tool that fails leaves its fact unknown,
 * and preflight does not check an unknown fact.
 */
export async function readMacFacts(deps: {
  exec: (file: string, args: string[]) => Promise<RuntimeExecResult>;
  resolve: (path: string) => string | null | undefined;
}): Promise<{arch?: string; macos?: string; freeBytes?: number; ramBytes?: number}> {
  const run = async (file: string, args: string[]) => {
    try {
      const result = await deps.exec(file, args);
      return result.status === 0 ? (result.stdout ?? "").trim() : null;
    } catch { return null; }
  };
  // hw.optional.arm64 is 1 on Apple Silicon even for a translated process.
  const arm = await run("/usr/sbin/sysctl", ["-n", "hw.optional.arm64"]);
  const arch = arm === "1" ? "arm64" : arm === "0" ? "x86_64" : (await run("/usr/bin/uname", ["-m"])) || undefined;
  const version = await run("/usr/bin/sw_vers", ["-productVersion"]);
  const macos = version && /^\d+(\.\d+)*$/.test(version) ? version : undefined;
  const memory = Number(await run("/usr/sbin/sysctl", ["-n", "hw.memsize"]));
  const ramBytes = Number.isFinite(memory) && memory > 0 ? memory : undefined;
  // Cue's own folder may not exist yet; ~/Library is on the same volume.
  const library = deps.resolve("~/Library");
  const df = library && library.startsWith("/") ? await run("/bin/df", ["-Pk", library]) : null;
  const available = Number(df?.split("\n")[1]?.trim().split(/\s+/)[3]);
  const freeBytes = Number.isFinite(available) && available >= 0 ? available * 1024 : undefined;
  return {arch, macos, freeBytes, ramBytes};
}

/**
 * Model pages the sidebar credits open. Keys come from the sidebar; the URLs
 * never do. These are the repositories pinned in models/manifest.json.
 */
export const CREDIT_LINKS = {
  gemma: "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm",
  aligner: "https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-4bit",
  "gemma-e4b": "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm",
} as const;

/** The browser opens the page; /usr/bin/open is a system tool, not a plugin file. */
export function openCreditLink(key: unknown, exec: (file: string, args: string[]) => unknown): boolean {
  if (typeof key !== "string" || !Object.prototype.hasOwnProperty.call(CREDIT_LINKS, key)) return false;
  void exec("/usr/bin/open", [CREDIT_LINKS[key as keyof typeof CREDIT_LINKS]]);
  return true;
}
