import type {Snapshot, Track} from "./types";
import {has, t} from "./strings";
import type {StringKey} from "./strings";

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
const languageKeys: Record<string, StringKey> = {en:"lang.en",eng:"lang.en",zh:"lang.zh",zho:"lang.zh",chi:"lang.zh",
  ja:"lang.ja",jpn:"lang.ja",ko:"lang.ko",kor:"lang.ko",yue:"lang.yue",
  de:"lang.de",es:"lang.es",fr:"lang.fr",it:"lang.it",pt:"lang.pt",ru:"lang.ru",
  el:"lang.el",ell:"lang.el",gre:"lang.el",ca:"lang.ca",pl:"lang.pl",pol:"lang.pl"};
/** A spoken-language name, or the upper-cased code when Cue has no name for it. */
export function languageName(code: string): string {
  const key = languageKeys[code];
  return key ? t(key) : code.toUpperCase();
}
export function originalLanguageLabel(code?: string): string {
  return code && code !== "und" ? t("lang.originalName", {name: languageName(code)}) : t("lang.original");
}
/**
 * The "original" option stays short enough for a narrow sidebar; how Cue knows
 * the spoken language goes in a hint line under Source language.
 */
export function originalLanguageChoice(code: string | undefined, status: string | undefined, state: {active: boolean; unclear: boolean}): {label: string; hint: string} {
  const known = !!code && code !== "und";
  const label = originalLanguageLabel(known ? code : undefined);
  if (known && status === "tentative") return {label, hint: t(code === "zh" ? "hint.tentativeChinese" : "hint.tentative", {name: languageName(code)})};
  if (known || !state.active) return {label, hint: ""};
  return {label, hint: t(state.unclear ? "hint.unclear" : "hint.detecting")};
}
/** One sidebar status: the headline a glancing viewer needs, then the detail and recovery. */
export type StatusTone = "off" | "working" | "ready" | "info" | "warning" | "error";
/** Coverage in the window after the playhead, as 0–1 fractions of that window. */
export type Coverage = {windowMs: number; installed: number[][]; prepared: number[][]; label: string};
export type CueStatus = {tone: StatusTone; title: string; detail?: string; retry?: boolean; reveal?: boolean; code?: string; coverage?: Coverage};
export function offStatus(): CueStatus { return {tone: "off", title: t("status.off")}; }
export function statusText(s: CueStatus): string { return s.detail ? t("status.osd", {title: s.title, detail: s.detail}) : s.title; }

/** Preparation failures stop Cue's work; the code stays for diagnostics, never as the headline. */
export function errorStatus(code: string, languageName?: string): CueStatus {
  if (code === "ALIGNMENT_LANGUAGE_UNSUPPORTED" && languageName)
    return {tone: "error", title: t("error.ALIGNMENT_LANGUAGE_UNSUPPORTED"), detail: t("error.ALIGNMENT_LANGUAGE_UNSUPPORTED.named", {name: languageName}), retry: true, code};
  const key = `error.${code}`;
  return has(key) && has(`${key}.detail`)
    ? {tone: "error", title: t(key), detail: t(`${key}.detail` as StringKey), retry: true, code}
    : {tone: "error", title: t("error.unknown"), detail: t("error.unknown.detail"), retry: true, code};
}
/** A failed plugin action (export, diagnostics) leaves prepared captions untouched. */
export function actionErrorStatus(code: string): CueStatus {
  const key = `error.${code}`;
  return has(key) && has(`${key}.detail`)
    ? {tone: "warning", title: t(key), detail: t(`${key}.detail` as StringKey), code}
    : {tone: "warning", title: t("error.action"), detail: t("error.action.detail"), code};
}
export function readyStatus(aheadMs: number, isPaused: boolean, cueHeldPlayback: boolean): CueStatus {
  // buffer_wall_ms is measured on player-acknowledged ranges, so it is "loaded", not merely prepared.
  const key = !isPaused ? "status.readyDetail" : cueHeldPlayback ? "status.readyDetailPressPlay" : "status.readyDetailPaused";
  return {tone: "ready", title: t("status.ready"), detail: t(key, {seconds: (aheadMs/1000).toFixed(0)})};
}
export function partialFailureStatus(aheadMs: number): CueStatus {
  return {tone: "warning", title: t("status.partial"), detail: t("status.partialDetail", {seconds: (aheadMs/1000).toFixed(0)}), retry: true};
}
function clip(ranges: number[][], from: number, to: number): number[][] {
  return ranges.map(([a, b]) => [Math.max(a, from), Math.min(b, to)]).filter(([a, b]) => b > a).sort((x, y) => x[0]-y[0]);
}
function subtract(ranges: number[][], minus: number[][]): number[][] {
  let out = ranges;
  for (const [ma, mb] of minus) out = out.flatMap(([a, b]) => [[a, Math.min(b, ma)], [Math.max(a, mb), b]].filter(([x, y]) => y > x));
  return out;
}
/** Where captions exist just ahead of the playhead; holes stay holes. */
export function coverageStrip(prepared: number[][], installed: number[][], positionMs: number, windowMs = 90000): Coverage {
  const end = positionMs + windowMs;
  const loaded = clip(installed, positionMs, end);
  const preparedOnly = subtract(clip(prepared, positionMs, end), loaded);
  const frac = (r: number[][]) => r.map(([a, b]) => [(a-positionMs)/windowMs, (b-positionMs)/windowMs]);
  const loadedNow = loaded.length && loaded[0][0] <= positionMs ? loaded[0][1]-positionMs : 0;
  const preparedMs = preparedOnly.reduce((total, [a, b]) => total + b-a, 0);
  const values = {loaded: Math.round(loadedNow/1000), prepared: Math.round(preparedMs/1000), window: Math.round(windowMs/1000)};
  const key = loadedNow ? (preparedMs ? "coverage.loadedAndPrepared" : "coverage.loaded") : (preparedMs ? "coverage.nothingAndPrepared" : "coverage.nothing");
  return {windowMs, installed: frac(loaded), prepared: frac(preparedOnly), label: t(key, values)};
}
/** Checks a user-typed MKV filename before any file is written. */
export function remuxFilename(response: string, suggested: string, folder: string, exists: (path: string) => boolean): {output?: string; error?: string} {
  const name = (response.trim() || suggested).replace(/\.(mp4|mov|m4v|webm|ts)$/i, ".mkv");
  const filename = name.toLowerCase().endsWith(".mkv") ? name : `${name}.mkv`;
  if (name === "." || name === ".." || name.startsWith(".") || name.endsWith(".") || filename.length > 240 || /[/\\\u0000-\u001f]/.test(name))
    return {error: t("remux.filenameInvalid")};
  const output = `${folder.replace(/\/+$/, "")}/${filename}`;
  if (exists(output)) return {output, error: t("remux.filenameExists")};
  return {output};
}
export function preparationStatus(snapshot: Pick<Snapshot, "stage" | "stage_elapsed_s" | "skipped_language_ranges">): CueStatus {
  const stageKey = `stage.${snapshot.stage}`;
  if (has(stageKey)) {
    const stage = t(stageKey), elapsed = snapshot.stage_elapsed_s;
    const detail = elapsed && elapsed >= 5 ? t("status.stageElapsed", {stage, seconds: Math.floor(elapsed)}) : t("status.stage", {stage});
    return {tone: "working", title: t("status.preparing"), detail};
  }
  if (snapshot.skipped_language_ranges?.length) return {tone: "warning", title: t("status.unclear"), detail: t("status.unclearDetail"), retry: true};
  return {tone: "working", title: t("status.preparing"), detail: t("status.nearPlayhead")};
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
