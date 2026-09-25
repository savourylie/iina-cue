import {preflight, startInstall, type PreflightFacts} from "./install-runtime";
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
  /** Paths are relative to the helper API; the client adds its /v1 prefix. */
  installRuntime(onProgress: (done: number, total: number) => void, onUnpack: () => void): Promise<{ok: boolean; reason?: string}>;
  /** Pause between polls of a running model download. */
  wait(ms: number): Promise<void>;
}

/** Helper phases that end a model download without finishing it. */
const STOPPED = new Set(["error", "cancelled", "interrupted"]);

export function createSetupController(host: SetupHost) {
  let previous: SetupPhase | undefined;
  let started = false;
  let running = false;
  let runtimeProgress: {done: number; total: number} | null = null;
  let unpacking = false;

  /** The helper answers only once a runtime is installed; null means it cannot yet. */
  async function helperStatus(): Promise<SetupStatus | null> {
    try { return await host.rpc("GET", "/setup"); } catch { return null; }
  }

  async function gate(reported: SetupStatus | null) {
    const facts = await host.facts();
    // Once the helper answers, the runtime is on disk and it knows the model bytes still missing.
    const bytesNeeded = reported?.bytes_needed ?? facts.bytesNeeded;
    return {bytesNeeded, result: preflight({...facts, bytesNeeded, freeBytes: reported?.free_disk_bytes ?? facts.freeBytes})};
  }

  async function publish(reason?: string, known?: SetupStatus | null) {
    const reported = known === undefined ? await helperStatus() : known;
    const status = reported ?? {};
    const {bytesNeeded, result} = await gate(reported);
    const helperPhase = status.progress?.phase;
    const phase: SetupPhase = !result.ok ? "unsupported"
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
    });
    previous = phase;
    host.post(view);
    return view;
  }

  async function runSetup() {
    const first = await helperStatus();
    const {result} = await gate(first);
    if (!result.ok) return publish(undefined, first);
    started = true;
    await publish(undefined, first);
    if (!first) {
      // No helper yet: fetch and unpack the runtime before anything else.
      runtimeProgress = null;
      unpacking = false;
      // No helper to ask while its runtime downloads: known = null skips the request.
      const installed = await host.installRuntime(
        (done, total) => { if (!unpacking) { runtimeProgress = {done, total}; void publish(undefined, null); } },
        () => { unpacking = true; void publish(undefined, null); },
      );
      unpacking = false;
      if (!installed.ok) return publish(installed.reason);
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
    refresh: () => publish(),
    async start() {
      startInstall(true);
      if (running) return;
      running = true;
      try { return await runSetup(); } finally { running = false; }
    },
  };
}
