import {curlResumeArgs, maySwap} from "./install-runtime";
import {INSTALLED_SUPPORT} from "./launch";
import {t} from "./strings";

export const RUNTIME_ARCHIVE_URL = "https://github.com/savourylie/iina-cue/releases/download/runtime-0.1.5/runtime-0.1.5.tar.xz";
export const RUNTIME_ARCHIVE_SHA256 = "70218fd01793d234d280401420aab1dfaf0ba874098a17a9479e3ffbaa91197f";
export const RUNTIME_ARCHIVE_BYTES = 270969508;

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
}): Promise<{ok: true} | {ok: false; reason: string}> {
  const decision = maySwap({remuxActive: deps.remuxActive, sessions: deps.sessions});
  if (!decision.ok) return {ok: false, reason: t("sidebar.setupRestart")};
  const support = deps.resolve(INSTALLED_SUPPORT);
  if (!support || !support.startsWith("/")) return {ok: false, reason: t("sidebar.setupNoFolder")};
  const partial = `${support}/runtime.tar.xz.partial`;
  const curl = curlResumeArgs(RUNTIME_ARCHIVE_URL, partial);
  const downloaded = await deps.exec(curl[0], curl.slice(1));
  if (downloaded.status !== 0) return {ok: false, reason: t("sidebar.setupDownloadStopped")};
  const unpack = unpackRuntimeInvocation(partial, `${support}/runtime`, RUNTIME_ARCHIVE_SHA256);
  const unpacked = await deps.exec(unpack.file, unpack.args);
  if (unpacked.status === 2) return {ok: false, reason: t("sidebar.setupChecksum")};
  if (unpacked.status !== 0) return {ok: false, reason: t("sidebar.setupUnpackFailed")};
  return {ok: true};
}

/** Must match release/runtime-0.1.5.json and models/manifest.json. */
export const RUNTIME_MINIMUM_MACOS = "27.0";
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
