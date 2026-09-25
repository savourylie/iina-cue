import {t} from "./strings";

export type SetupPhase = "unsupported" | "download" | "runtime" | "unpacking" | "models" | "verifying" | "smoke" | "done" | "failed";

export interface SetupView {
  showCard: boolean;
  showControls: boolean;
  ready: boolean;
  primary: string | null;
  progress: number | null;
  bytes: string;
  detail: string;
  announce: string | null;
}

const PHASE_KEY = {
  unsupported: "sidebar.setupPhaseUnsupported",
  download: "sidebar.setupPhaseDownload",
  runtime: "sidebar.setupPhaseRuntime",
  unpacking: "sidebar.setupPhaseUnpacking",
  models: "sidebar.setupPhaseModels",
  verifying: "sidebar.setupPhaseVerifying",
  smoke: "sidebar.setupPhaseSmoke",
  done: "sidebar.setupPhaseDone",
  failed: "sidebar.setupPhaseFailed",
} as const;

/** Decimal units, as in "about 3.8 GB" in the setup text. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(0, Math.round(bytes / 1e6))} MB`;
}

/** One view of setup. A repeated poll of the same phase does not produce a new announcement. */
export function setupView(input: {phase: SetupPhase; previous?: SetupPhase; bytesDone?: number; bytesTotal?: number; diskBytes?: number; reason?: string}): SetupView {
  const showCard = input.phase !== "done";
  const busy = input.phase === "runtime" || input.phase === "models";
  const total = input.bytesTotal ?? 0;
  const done = input.bytesDone ?? 0;
  const reasonPhase = input.phase === "unsupported" || input.phase === "failed";
  // The card's heading stays "Set up Cue"; the detail line names the current step.
  // With nothing left to fetch, setup only runs the short test clip.
  const nothingToFetch = input.phase === "download" && input.diskBytes === 0;
  const detail = nothingToFetch ? t("sidebar.setupNothingToFetch")
    : input.phase === "download" ? t("sidebar.setupDisk", {size: formatBytes(input.diskBytes ?? 0)})
    : reasonPhase ? (input.reason ?? "")
    : t(PHASE_KEY[input.phase]);
  return {
    showCard,
    showControls: !showCard,
    ready: input.phase === "done",
    primary: nothingToFetch ? t("sidebar.setupContinue") : input.phase === "download" ? t("sidebar.setupDownload") : input.phase === "failed" ? t("sidebar.setupRetry") : null,
    progress: busy && total > 0 ? Math.floor((100 * done) / total) : null,
    bytes: busy && total > 0 ? t("sidebar.setupBytes", {done: formatBytes(done), total: formatBytes(total), percent: Math.floor((100 * done) / total)}) : "",
    detail,
    announce: input.phase === input.previous ? null : t(PHASE_KEY[input.phase]),
  };
}
