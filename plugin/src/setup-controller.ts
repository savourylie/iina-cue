import {compareVersions, preflight, startInstall, type PreflightFacts} from "./install-runtime";
import {setupView, type SetupPhase, type SetupView} from "./setup-view";
import {t} from "./strings";

export interface SetupStatus {
  files_ready?: boolean;
  bytes_total?: number;
  bytes_needed?: number;
  free_disk_bytes?: number;
  progress?: {bytes_done?: number; bytes_total?: number; phase?: string};
  smoke?: {passed?: boolean; reason?: string} | null;
}

export interface SetupHost {
  rpc(method: "GET" | "POST", path: string, body?: Record<string, unknown>): Promise<SetupStatus>;
  post(view: SetupView): void;
  /** Facts about this Mac. Runtime plus model bytes when the helper cannot answer yet. */
  facts(): Promise<PreflightFacts>;
  /**
   * Download and unpack the published runtime. With update set, an installed helper is
   * running: it is stopped only after the download passes its checksum, and not at all while in use.
   */
  installRuntime(onProgress: (done: number, total: number) => void, onUnpack: () => void, update: boolean): Promise<{ok: boolean; reason?: string}>;
  /** Pause between polls of a running model download. */
  wait(ms: number): Promise<void>;
  /** The helper that answered: the version it reports, and whether it runs from Cue's installed runtime. */
  helper?(): {version: string | null; installed: boolean} | null;
  /** The runtime version this plugin installs, and its download size. */
  runtime?: {version: string; bytes: number};
  /** An update run has ended, whether or not it replaced the helper. */
  updateFinished?(): void;
}

/** Helper phases that end a model download without finishing it. */
const STOPPED = new Set(["error", "cancelled", "interrupted"]);

export function createSetupController(host: SetupHost) {
  let previous: SetupPhase | undefined;
  let started = false;
  let running = false;
  let runtimeProgress: {done: number; total: number} | null = null;
  let unpacking = false;
  // An update is running; while the runtime is swapped, nothing may start the old helper again.
  let updating = false;
  let swapping = false;

  /**
   * Only Cue's installed runtime is replaced, and only by a newer one. A development
   * checkout, a helper chosen in preferences, or an unreported version is left alone.
   */
  function outdated(reported: SetupStatus | null): boolean {
    const helper = reported && host.runtime ? host.helper?.() : null;
    return !!(helper?.installed && helper.version && host.runtime && compareVersions(helper.version, host.runtime.version) < 0);
  }

  /** The helper answers only once a runtime is installed; null means it cannot yet. */
  async function helperStatus(): Promise<SetupStatus | null> {
    try { return await host.rpc("GET", "/setup"); } catch { return null; }
  }

  // Facts are read with system tools through IINA's exec, which answers one call at a time:
  // during a download or unpack they would wait for it. A run reuses the facts it began with.
  let facts: PreflightFacts | null = null;
  async function gate(reported: SetupStatus | null) {
    if (!running || !facts) facts = await host.facts();
    // Once the helper answers, the runtime is on disk and it knows the model bytes still missing.
    // An update keeps the models, so while its helper is down only the runtime is fetched.
    const bytesNeeded = reported?.bytes_needed ?? (updating && host.runtime ? host.runtime.bytes : facts.bytesNeeded);
    return {bytesNeeded, result: preflight({...facts, bytesNeeded, freeBytes: reported?.free_disk_bytes ?? facts.freeBytes})};
  }

  async function publish(reason?: string, known?: SetupStatus | null) {
    const reported = known === undefined ? await helperStatus() : known;
    const status = reported ?? {};
    const {bytesNeeded, result} = await gate(reported);
    const helperPhase = status.progress?.phase;
    const old = outdated(reported);
    const phase: SetupPhase = !result.ok ? "unsupported"
      // A failed update leaves the old helper answering; the failure is still what to show.
      : (updating || old) && reason ? "failed"
      : old && !running ? "update"
      : status.smoke?.passed && status.files_ready ? "done"
      : reason || (helperPhase && STOPPED.has(helperPhase)) || status.smoke?.passed === false ? "failed"
      : helperPhase === "downloading" ? "models"
      : running && unpacking ? "unpacking"
      : helperPhase === "smoking" || (running && status.files_ready) ? "smoke"
      : running ? "runtime"
      : started ? "failed"
      : "download";
    const view = setupView({
      phase,
      previous,
      bytesDone: phase === "runtime" ? runtimeProgress?.done : status.progress?.bytes_done,
      bytesTotal: phase === "runtime" ? runtimeProgress?.total : status.progress?.bytes_total ?? status.bytes_total,
      diskBytes: bytesNeeded,
      reason: result.ok ? (reason ?? status.smoke?.reason) : result.reason,
      mode: updating || old ? "update" : "setup",
      updateBytes: host.runtime?.bytes,
    });
    previous = phase;
    host.post(view);
    return view;
  }

  async function runSetup() {
    let first = await helperStatus();
    const {result} = await gate(first);
    if (!result.ok) return publish(undefined, first);
    started = true;
    updating = outdated(first);
    if (!first || updating) {
      // No helper yet, or an older one: fetch and unpack the runtime before anything else.
      runtimeProgress = null;
      unpacking = false;
      swapping = true;
      // Nothing is asked of a helper while its runtime downloads: known = null skips the request.
      await publish(undefined, null);
      const installed = await host.installRuntime(
        (done, total) => { if (!unpacking) { runtimeProgress = {done, total}; void publish(undefined, null); } },
        () => { unpacking = true; void publish(undefined, null); },
        updating,
      ).finally(() => { swapping = false; });
      unpacking = false;
      if (!installed.ok) return publish(installed.reason);
      // The new runtime's helper answers from here on; the test clip below checks it.
      if (updating) {
        first = await helperStatus();
        // Retry then installs the published runtime again.
        if (!first) return publish(t("sidebar.updateNoHelper"), null);
      }
    } else {
      await publish(undefined, first);
    }
    try {
      // Files already in place need no download request, only the smoke test.
      let status = first?.files_ready ? first
        : await host.rpc("POST", "/setup/actions", {action: first?.progress?.bytes_done ? "resume" : "start"});
      // The download runs in the helper's own thread; the smoke test needs its files.
      while (status.progress?.phase === "downloading") {
        await publish(undefined, status);
        await host.wait(1000);
        status = await host.rpc("GET", "/setup");
      }
      if (!status.files_ready) return publish(undefined, status);
      await publish(undefined, status);
      // The helper runs the smoke test on its inference worker in the background.
      status = await host.rpc("POST", "/setup/actions", {action: "smoke"});
      while (status.progress?.phase === "smoking") {
        await publish(undefined, status);
        await host.wait(1000);
        status = await host.rpc("GET", "/setup");
      }
      return publish(undefined, status);
    } catch {
      return publish(t("sidebar.setupModelsStopped"));
    }
  }

  return {
    // While the runtime is swapped, asking the helper would start the old one again.
    refresh: () => publish(undefined, swapping ? null : undefined),
    /** True while a runtime download or swap runs; other requests to the helper wait. */
    swapping: () => swapping,
    async start() {
      startInstall(true);
      if (running) return;
      running = true;
      try { return await runSetup(); } finally {
        running = false;
        if (updating) { updating = false; host.updateFinished?.(); }
      }
    },
  };
}
