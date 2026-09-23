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
/** One sidebar status: the headline a glancing viewer needs, then the detail and recovery. */
export type StatusTone = "off" | "working" | "ready" | "info" | "warning" | "error";
export type CueStatus = {tone: StatusTone; title: string; detail?: string; retry?: boolean; code?: string};
export const OFF_STATUS: CueStatus = {tone: "off", title: "AI subtitles are off"};
export function statusText(s: CueStatus): string { return s.detail ? `${s.title}. ${s.detail}` : s.title; }

const errorCopy: Record<string, [string, string]> = {
  SETUP_REQUIRED: ["Setup needed", "Cue's local models are not installed. Finish setup from Cue's preferences, then retry."],
  LANGUAGE_UNCERTAIN: ["Language not detected", "Choose the source language below, then retry."],
  ALIGNMENT_LANGUAGE_UNSUPPORTED: ["Language not supported", "Cue cannot time subtitles in this source language yet."],
  AUDIO_TRACK_MAPPING_AMBIGUOUS: ["Audio track not verified", "Cue could not confirm which audio track is playing, so it stopped preparing captions."],
  AUDIO_DELAY_UNSUPPORTED: ["Audio delay not supported", "Set the audio delay back to 0, then retry."],
  HELPER_DISCONNECTED: ["Subtitle engine disconnected", "Retry to reconnect."],
  HELPER_RESTART_REQUIRED: ["Subtitle engine update waiting", "Wait for the remux to finish or close other Cue windows, then retry."],
  MODEL_LOAD_FAILED: ["Speech model did not load", "Retry. If it keeps failing, save diagnostics from Advanced."],
  ALIGNMENT_FAILED: ["Caption timing failed", "These captions did not pass the timing check. Retry or keep playing."],
  TRANSLATION_FAILED: ["Translation failed", "The translation did not pass validation. Retry or choose the original language."],
  OUTPUT_EXISTS: ["File already exists", "Choose a different path. Cue never replaces existing files."],
  UNSAFE_PATH: ["Path not allowed", "Choose a new absolute .srt path in an existing folder."]
};
/** Preparation failures stop Cue's work; the code stays for diagnostics, never as the headline. */
export function errorStatus(code: string, languageName?: string): CueStatus {
  if (code === "ALIGNMENT_LANGUAGE_UNSUPPORTED" && languageName)
    return {tone: "error", title: "Language not supported", detail: `The speech was identified as ${languageName}. Cue cannot time subtitles in that language yet.`, retry: true, code};
  const [title, detail] = errorCopy[code] ?? ["Captions stopped", "Something went wrong while preparing captions. Retry or keep playing."];
  return {tone: "error", title, detail, retry: true, code};
}
/** A failed plugin action (export, diagnostics) leaves prepared captions untouched. */
export function actionErrorStatus(code: string): CueStatus {
  const [title, detail] = errorCopy[code] ?? ["Action failed", "Cue could not complete that action."];
  return {tone: "warning", title, detail, code};
}
export function readyStatus(aheadMs: number, isPaused: boolean, cueHeldPlayback: boolean): CueStatus {
  const ahead = `${(aheadMs/1000).toFixed(0)} s prepared ahead.`;
  const pause = !isPaused ? "" : cueHeldPlayback ? " Press play to continue." : " Video remains paused.";
  return {tone: "ready", title: "Captions ready", detail: ahead + pause};
}
export function partialFailureStatus(aheadMs: number): CueStatus {
  return {tone: "warning", title: "Later captions failed", detail: `${(aheadMs/1000).toFixed(0)} s of captions remain available. Keep playing or retry.`, retry: true};
}
export function preparationStatus(snapshot: Pick<Snapshot, "stage" | "stage_elapsed_s" | "skipped_language_ranges">): CueStatus {
  const seconds = snapshot.stage_elapsed_s && snapshot.stage_elapsed_s >= 5 ? ` · ${Math.floor(snapshot.stage_elapsed_s)} s` : "";
  const stages: Record<string, string> = {
    extracting: "Reading nearby audio",
    loading_model: "Loading the speech model",
    transcribing: "Transcribing nearby speech",
    identifying_language: "Identifying the spoken language",
    aligning: "Loading the aligner and timing spoken words",
    translating: "Translating timed captions"
  };
  if (snapshot.stage in stages) return {tone: "working", title: "Preparing captions", detail: `${stages[snapshot.stage]}…${seconds}`};
  if (snapshot.skipped_language_ranges?.length) return {tone: "warning", title: "Language unclear", detail: "Earlier audio had no clear language. Press play to check later audio, or choose a source language and retry.", retry: true};
  return {tone: "working", title: "Preparing captions", detail: "Working near the current position…"};
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
