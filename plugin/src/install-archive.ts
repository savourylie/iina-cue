import {execFile} from "node:child_process";
import {promisify} from "node:util";
import {maySwap} from "./install-runtime";
import {unpackRuntimeInvocation} from "./runtime-install";
import {t} from "./strings";

const exec = promisify(execFile);

/** Verify the archive and unpack it. The shell is the same one the plugin runs. */
export async function installVerifiedArchive(options: {
  archive: string;
  expectedSha256: string;
  destination: string;
  remuxActive?: boolean;
  sessions?: number;
}): Promise<{ok: true} | {ok: false; code: "SHA256_MISMATCH" | "HELPER_RESTART_REQUIRED" | "UNPACK_FAILED"; reason: string}> {
  const decision = maySwap({remuxActive: options.remuxActive ?? false, sessions: options.sessions ?? 0});
  if (!decision.ok) return {ok: false, code: decision.code, reason: t("sidebar.setupRestart")};
  const invocation = unpackRuntimeInvocation(options.archive, options.destination, options.expectedSha256);
  try {
    await exec(invocation.file, invocation.args, {encoding: "utf8"});
  } catch (error) {
    const raw = typeof error === "object" && error ? error as {status?: unknown; code?: unknown} : {};
    const status = Number(raw.status ?? raw.code);
    if (status === 2) return {ok: false, code: "SHA256_MISMATCH", reason: t("sidebar.setupChecksum")};
    return {ok: false, code: "UNPACK_FAILED", reason: t("sidebar.setupUnpackFailed")};
  }
  return {ok: true};
}
