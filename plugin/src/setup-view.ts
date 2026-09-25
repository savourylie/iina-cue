import {t} from "./strings";

export type SetupPhase = "unsupported" | "download" | "runtime" | "models" | "verifying" | "smoke" | "done" | "failed";

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
  models: "sidebar.setupPhaseModels",
  verifying: "sidebar.setupPhaseVerifying",
  smoke: "sidebar.setupPhaseSmoke",
  done: "sidebar.setupPhaseDone",
  failed: "sidebar.setupPhaseFailed",
} as const;

/** One view of setup. A repeated poll of the same phase does not produce a new announcement. */
export function setupView(input: {phase: SetupPhase; previous?: SetupPhase; bytesDone?: number; bytesTotal?: number; diskBytes?: number; reason?: string}): SetupView {
  const showCard = input.phase !== "done";
  const busy = input.phase === "runtime" || input.phase === "models";
  const total = input.bytesTotal ?? 0;
  const done = input.bytesDone ?? 0;
  const detail = input.phase === "download"
    ? t("sidebar.setupDisk", {bytes: input.diskBytes ?? 0})
    : input.phase === "unsupported" || input.phase === "failed" ? (input.reason ?? "") : "";
  return {
    showCard,
    showControls: !showCard,
    ready: input.phase === "done",
    primary: input.phase === "download" ? t("sidebar.setupDownload") : input.phase === "failed" ? t("sidebar.setupRetry") : null,
    progress: busy && total > 0 ? Math.floor((100 * done) / total) : null,
    bytes: busy ? `${done} / ${total}` : "",
    detail,
    announce: input.phase === input.previous ? null : t(PHASE_KEY[input.phase]),
  };
}
