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
  /** A step is running whose length is unknown, such as unpacking or the test clip. */
  indeterminate: boolean;
  bytes: string;
  detail: string;
  announce: string | null;
  /** An update is offered: a small button at the top of the sidebar, with its size in the hint. */
  updateButton: string | null;
  updateHint: string;
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
  update: "sidebar.updateAvailable",
  runtime: "sidebar.updatePhaseRuntime",
  unpacking: "sidebar.updatePhaseUnpacking",
  smoke: "sidebar.updatePhaseSmoke",
  done: "sidebar.updatePhaseDone",
  failed: "sidebar.updatePhaseFailed",
} as const;

/** Steps that run without a byte count still show that something is happening. */
const WORKING = new Set<SetupPhase>(["runtime", "unpacking", "models", "verifying", "smoke"]);

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
  const offer = input.phase === "update";
  // An offered update is only a button; a running or failed one is a short status block.
  const showCard = input.phase !== "done" && !offer;
  const busy = input.phase === "runtime" || input.phase === "models";
  const total = input.bytesTotal ?? 0;
  const done = input.bytesDone ?? 0;
  const measurable = busy && total > 0;
  const reasonPhase = input.phase === "unsupported" || input.phase === "failed";
  const keys = update ? UPDATE_PHASE_KEY : PHASE_KEY;
  // The card's heading names setup or the update; the detail line names the current step.
  // With nothing left to fetch, setup only runs the short test clip.
  const nothingToFetch = input.phase === "download" && input.diskBytes === 0;
  const detail = nothingToFetch ? t("sidebar.setupNothingToFetch")
    : input.phase === "download" ? t("sidebar.setupDisk", {size: formatBytes(input.diskBytes ?? 0)})
    : offer ? ""
    : reasonPhase ? (input.reason ?? "")
    : t(keys[input.phase]);
  return {
    showCard,
    // The installed helper serves captions until the swap, and each window turns them
    // off and on again by itself, so an update never takes the controls away.
    showControls: !showCard || update,
    ready: input.phase === "done",
    title: t(!update ? "sidebar.setupTitle" : input.phase === "failed" ? "sidebar.updateFailedTitle" : "sidebar.updateTitle"),
    intro: update ? "" : t("sidebar.setupIntro"),
    credits: !update,
    primary: nothingToFetch ? t("sidebar.setupContinue") : input.phase === "download" ? t("sidebar.setupDownload")
      : input.phase === "failed" ? t("sidebar.setupRetry") : null,
    progress: measurable ? Math.floor((100 * done) / total) : null,
    indeterminate: !measurable && WORKING.has(input.phase),
    bytes: measurable ? t("sidebar.setupBytes", {done: formatBytes(done), total: formatBytes(total), percent: Math.floor((100 * done) / total)}) : "",
    detail,
    announce: input.phase === input.previous ? null : t(keys[input.phase]),
    updateButton: offer ? t("sidebar.updateButton") : null,
    updateHint: offer ? t("sidebar.updateHint", {size: formatBytes(input.updateBytes ?? 0)}) : "",
  };
}
