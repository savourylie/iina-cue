import {t} from "./strings";

export type SetupPhase = "unsupported" | "download" | "update" | "runtime" | "unpacking" | "models" | "verifying" | "smoke" | "done" | "failed";

export interface SetupView {
  showCard: boolean;
  showControls: boolean;
  ready: boolean;
  /** The card's heading and first paragraph: first-run setup, or an update of an installed helper. */
  title: string;
  intro: string;
  /** Model credits belong to first-run setup, which downloads the models. */
  credits: boolean;
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
  update: "sidebar.updateTitle",
} as const;

/** An update names its own steps; it has no model download. */
const UPDATE_PHASE_KEY = {
  ...PHASE_KEY,
  runtime: "sidebar.updatePhaseRuntime",
  unpacking: "sidebar.updatePhaseUnpacking",
  smoke: "sidebar.updatePhaseSmoke",
  done: "sidebar.updatePhaseDone",
  failed: "sidebar.updatePhaseFailed",
} as const;

/** Decimal units, as in "about 3.8 GB" in the setup text. */
export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(0, Math.round(bytes / 1e6))} MB`;
}

/** One view of setup. A repeated poll of the same phase does not produce a new announcement. */
export function setupView(input: {
  phase: SetupPhase; previous?: SetupPhase; bytesDone?: number; bytesTotal?: number; diskBytes?: number; reason?: string;
  /** "update" replaces an installed helper that is older than this plugin needs. */
  mode?: "setup" | "update";
  /** The update's download size, shown before it starts. */
  updateBytes?: number;
}): SetupView {
  const update = input.mode === "update";
  const showCard = input.phase !== "done";
  const busy = input.phase === "runtime" || input.phase === "models";
  const total = input.bytesTotal ?? 0;
  const done = input.bytesDone ?? 0;
  const reasonPhase = input.phase === "unsupported" || input.phase === "failed";
  const keys = update ? UPDATE_PHASE_KEY : PHASE_KEY;
  // The card's heading names setup or the update; the detail line names the current step.
  // With nothing left to fetch, setup only runs the short test clip.
  const nothingToFetch = input.phase === "download" && input.diskBytes === 0;
  const detail = nothingToFetch ? t("sidebar.setupNothingToFetch")
    : input.phase === "download" ? t("sidebar.setupDisk", {size: formatBytes(input.diskBytes ?? 0)})
    : input.phase === "update" ? t("sidebar.updateDetail", {size: formatBytes(input.updateBytes ?? 0)})
    : reasonPhase ? (input.reason ?? "")
    : t(keys[input.phase]);
  return {
    showCard,
    // The installed helper keeps working until the user starts the update, and after one fails.
    showControls: !showCard || (update && (input.phase === "update" || input.phase === "failed")),
    ready: input.phase === "done",
    title: t(update ? "sidebar.updateTitle" : "sidebar.setupTitle"),
    intro: t(update ? "sidebar.updateIntro" : "sidebar.setupIntro"),
    credits: !update,
    primary: nothingToFetch ? t("sidebar.setupContinue") : input.phase === "download" ? t("sidebar.setupDownload")
      : input.phase === "update" ? t("sidebar.updateButton") : input.phase === "failed" ? t("sidebar.setupRetry") : null,
    progress: busy && total > 0 ? Math.floor((100 * done) / total) : null,
    bytes: busy && total > 0 ? t("sidebar.setupBytes", {done: formatBytes(done), total: formatBytes(total), percent: Math.floor((100 * done) / total)}) : "",
    detail,
    announce: input.phase === input.previous ? null : t(keys[input.phase]),
  };
}
