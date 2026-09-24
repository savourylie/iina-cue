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

const TITLES: Record<SetupPhase, string> = {
  unsupported: "This Mac cannot run Cue.",
  download: "Set up Cue",
  runtime: "Downloading the helper",
  models: "Downloading the speech models",
  verifying: "Checking the download",
  smoke: "Trying a short clip",
  done: "Cue is ready",
  failed: "Setup did not finish",
};

/** One view of setup. A repeated poll of the same phase does not produce a new announcement. */
export function setupView(input: {phase: SetupPhase; previous?: SetupPhase; bytesDone?: number; bytesTotal?: number; reason?: string}): SetupView {
  const showCard = input.phase !== "done";
  const busy = input.phase === "runtime" || input.phase === "models";
  const total = input.bytesTotal ?? 0;
  const done = input.bytesDone ?? 0;
  return {
    showCard,
    showControls: !showCard,
    ready: input.phase === "done",
    primary: input.phase === "download" ? "Download" : input.phase === "failed" ? "Retry" : null,
    progress: busy && total > 0 ? Math.floor((100 * done) / total) : null,
    bytes: busy ? `${done} / ${total}` : "",
    detail: input.phase === "unsupported" || input.phase === "failed" ? (input.reason ?? "") : "",
    announce: input.phase === input.previous ? null : TITLES[input.phase],
  };
}
