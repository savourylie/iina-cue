import type {Snapshot, Track} from "./types";

export function ownedTrack(tracks: Track[], path: string): Track | undefined {
  return tracks.find(t => t.type === "sub" && t.external === true && t["external-filename"] === path);
}
export function targetSubtitleExists(tracks: Track[], target: string): boolean {
  const languages = target === "zh-TW" ? ["zh-TW", "zh-Hant", "zh-Hant-TW"]
    : target === "zh-CN" ? ["zh-CN", "zh-Hans", "zh-Hans-CN"]
    : target === "en" ? ["en", "eng"] : target === "ja" ? ["ja", "jpn"]
    : target === "ko" ? ["ko", "kor"] : [target];
  return tracks.some(t => t.type === "sub" && !t.forced && !/signs|songs|forced|招牌/i.test(t.title || "") && languages.includes(t.lang || ""));
}
export function originalLanguageLabel(code?: string): string {
  const names: Record<string, string> = {en:"English",eng:"English",zh:"Chinese",zho:"Chinese",chi:"Chinese",
    ja:"Japanese",jpn:"Japanese",ko:"Korean",kor:"Korean",yue:"Cantonese",
    de:"German",es:"Spanish",fr:"French",it:"Italian",pt:"Portuguese",ru:"Russian",
    el:"Greek",ell:"Greek",gre:"Greek",ca:"Catalan",pl:"Polish",pol:"Polish"};
  const name = names[code || ""];
  return name ? `${name} (original)` : code && code !== "und" ? `${code.toUpperCase()} (original)` : "Original language (detecting…)";
}
export function originalLanguageEvidenceLabel(code?: string, status?: string): string {
  if (status === "tentative" && code && code !== "und") {
    const name = originalLanguageLabel(code).replace(" (original)", "");
    return `Original language (transcript: ${name}; unverified)`;
  }
  return originalLanguageLabel(code);
}
export function preparationStatus(snapshot: Pick<Snapshot, "stage" | "stage_elapsed_s" | "skipped_language_ranges">): string {
  const seconds = snapshot.stage_elapsed_s && snapshot.stage_elapsed_s >= 5 ? ` · ${Math.floor(snapshot.stage_elapsed_s)} s` : "";
  const stages: Record<string, string> = {
    extracting: "Reading nearby audio",
    loading_model: "Loading the speech model",
    transcribing: "Transcribing nearby speech",
    identifying_language: "Identifying the spoken language",
    aligning: "Loading the aligner and timing spoken words",
    translating: "Translating timed captions"
  };
  if (snapshot.stage in stages) return `${stages[snapshot.stage]}…${seconds}`;
  if (snapshot.skipped_language_ranges?.length) return "Language was unclear in earlier audio. Press play to check later audio, or choose a source language and retry.";
  return "Preparing captions near the current position…";
}
export function acceptSnapshot(s: {session_id: string; seek_epoch: number; instance_id: string}, id: string, epoch: number, instance: string): boolean {
  return s.session_id === id && s.seek_epoch === epoch && s.instance_id === instance;
}

/** Ambiguous pause intent is conservative: ready never automatically presses play. */
export class PlaybackIntent {
  holding = false;
  bypass = false;
  hold(paused: boolean): boolean {
    if (this.bypass || paused) return false;
    this.holding = true;
    return true;
  }
  userPlay() { this.holding = false; this.bypass = true; }
  ready() { this.holding = false; }
  reset() { this.holding = false; this.bypass = false; }
}
