import {rpc, disposeClient} from "./client";
import {acceptSnapshot, originalLanguageLabel, ownedTrack, PlaybackIntent, targetSubtitleExists} from "./control";
import {mediaSnapshot, number, paused, SubtitleRenderer, tracks} from "./player";
import type {Snapshot} from "./types";
import {rendererSmoke} from "./smoke";
import {SubtitleSize, SubtitleStyle, validSubtitleSize} from "./style";

const renderer = new SubtitleRenderer();
const intent = new PlaybackIntent();
const subtitleStyle = new SubtitleStyle(iina.mpv);
const subtitleSize = new SubtitleSize(iina.mpv);
let enabled = false;
let generation = 0;
let session: Snapshot | undefined;
let epoch = 0;
let seq = 0;
let busy = false;
let selected = false;
let latestStatus = "AI subtitles are off";
let lastStage = "";
let seekTimer: ReturnType<typeof setTimeout> | undefined;
let awaitingSeek = false;
let sidebarLoaded = false;
const events: [string, string][] = [];
const trace: object[] = [];
const targets = new Set(["original", "zh-TW", "zh-CN", "en", "ja", "ko"]);
function target() {
  const value = iina.preferences.get("target");
  return targets.has(value) ? value : "original";
}
function syncSettings() {
  const detected = session?.language?.code;
  const manual = iina.preferences.get("source");
  const originalCode = detected && detected !== "und" ? detected : manual !== "auto" ? manual : undefined;
  if (sidebarLoaded) iina.sidebar.postMessage("cue-settings", {
    target: target(), pauseUntilReady: iina.preferences.get("pauseUntilReady") === true,
    subtitleBox: iina.preferences.get("subtitleBox") === true,
    subtitleSize: validSubtitleSize(iina.preferences.get("subtitleSize")) ?? subtitleSize.current(),
    originalLabel: originalLanguageLabel(originalCode)
  });
}
function traceEvent(event: string, data: object = {}) {
  trace.push({event,at:Date.now(),generation,epoch,...data});
  if (trace.length>32) trace.shift();
}
const errorText: Record<string, string> = {
  SETUP_REQUIRED: "Local models are not installed. Complete Cue setup first.",
  LANGUAGE_UNCERTAIN: "Language could not be detected. Choose the source language and retry.",
  ALIGNMENT_LANGUAGE_UNSUPPORTED: "This source language cannot be aligned yet.",
  AUDIO_TRACK_MAPPING_AMBIGUOUS: "The audio track could not be verified. Subtitle preparation stopped.",
  AUDIO_DELAY_UNSUPPORTED: "This preview does not support nonzero audio delay.",
  HELPER_DISCONNECTED: "The local subtitle engine disconnected. You can retry.",
  MODEL_LOAD_FAILED: "The model failed to load. Check the local diagnostic log.",
  ALIGNMENT_FAILED: "Subtitle alignment failed validation. Retry or keep playing.",
  TRANSLATION_FAILED: "The translation failed validation. Retry or choose the original language."
};
function status(text: string, osd = false) {
  const changed = latestStatus !== text;
  latestStatus = text;
  if (sidebarLoaded) iina.sidebar.postMessage("cue-status", {text});
  if (osd && changed) iina.core.osd(text);
}
function showError(e: unknown) {
  const code = String(e).replace(/^Error: /, "");
  status(errorText[code] || `Subtitle preparation failed (${code}). Retry or keep playing.`, true);
}
function hold() {
  if (iina.preferences.get("pauseUntilReady") === true && intent.hold(paused())) iina.mpv.set("pause", true);
}
function syncSubtitleAppearance() {
  const own = renderer.path && ownedTrack(tracks(), renderer.path);
  if (enabled && own && String(own.id) === iina.mpv.getString("sid")) {
    if (iina.preferences.get("subtitleBox") === true) {
      try { subtitleStyle.enable(); } catch (error) { traceEvent("style_error", {error:String(error)}); status("Could not apply the black subtitle background; captions still work.", true); }
    } else subtitleStyle.restore();
    const size = validSubtitleSize(iina.preferences.get("subtitleSize"));
    if (size !== undefined) {
      try { subtitleSize.apply(size); } catch (error) { traceEvent("size_error", {error:String(error)}); status("Could not change subtitle size; captions still work.", true); }
    } else subtitleSize.restore();
  } else { subtitleStyle.restore(); subtitleSize.restore(); }
}
async function stop() {
  const previous = session;
  generation++; enabled = false; session = undefined; epoch = 0; seq = 0; selected = false;
  intent.reset(); subtitleStyle.restore(); subtitleSize.restore(); renderer.remove(); syncSettings();
  if (seekTimer) clearTimeout(seekTimer);
  awaitingSeek = false;
  if (previous) { try { await rpc("DELETE", `/sessions/${previous.session_id}`); } catch {} }
}
async function start() {
  traceEvent("start",{position:number("time-pos")});
  setupSidebar();
  const requestedGeneration = generation + 1;
  await stop();
  if (generation !== requestedGeneration) return;
  const token = generation;
  try {
    const media = mediaSnapshot();
    enabled = true; hold(); status("Starting the local subtitle engine…", true);
    const created = await rpc<Snapshot>("POST", "/sessions", {...media,
      request_id: `${Date.now()}-${generation}`, settings: {target: target(), source: iina.preferences.get("source")}});
    if (generation !== token || !enabled) { await rpc("DELETE", `/sessions/${created.session_id}`); return; }
    session = created;
    // A cache hit may know the source language in the very first snapshot.
    // consume() compares snapshots against session, so publish that label now.
    syncSettings();
    await consume(created, token);
  } catch (e) { traceEvent("start_error",{error:String(e)}); if (generation === token) { enabled = false; showError(e); } }
}
async function consume(snapshot: Snapshot, token: number) {
  if (!session || token !== generation || !acceptSnapshot(snapshot, session.session_id, epoch, session.instance_id)) return;
  const priorLanguage = session.language?.code;
  session = snapshot;
  if (snapshot.language?.code !== priorLanguage) syncSettings();
  const a = snapshot.artifact;
  if (a && a.revision > renderer.installed) {
    const valid = () => enabled && generation === token && !!session && acceptSnapshot(snapshot, session.session_id, epoch, session.instance_id);
    try {
      await renderer.install(a, !selected, valid);
      if (!valid()) return;
      if (a.cue_count) selected = true;
      syncSubtitleAppearance();
      const acknowledged = await rpc<Snapshot>("POST", `/sessions/${snapshot.session_id}/render-ack`, {
        revision: a.revision, sha256: a.sha256, seek_epoch: epoch, success: true});
      if (!valid()) return;
      session = acknowledged;
    } catch (e) {
      if (String(e).includes("STALE_ACK")) {renderer.installed = 0; return;}
      if (valid()) { await rpc("POST", `/sessions/${snapshot.session_id}/render-ack`, {revision:a.revision,sha256:a.sha256,seek_epoch:epoch,success:false}); showError(e); }
      return;
    }
  }
  if (!session || token !== generation) return;
  if (snapshot.error) {
    if (session.ready) status(`${(session.buffer_wall_ms/1000).toFixed(0)} seconds of captions remain available; later processing failed. Keep playing or retry.`,true);
    else showError(snapshot.error.code);
    return;
  }
  if (session.ready) {
    const wasHolding = intent.holding;
    intent.ready();
    status(`Captions ready · ${(session.buffer_wall_ms/1000).toFixed(0)} s ahead${paused() ? wasHolding ? " · Press play to continue" : " · Video remains paused" : ""}`, wasHolding);
  } else {
    if (session.buffer_wall_ms <= 1000) hold();
    const stage = session.stage === "inference"
      ? target() === "original" ? "Transcribing and aligning original-language captions…" : "Transcribing, aligning, and translating…"
      : "Preparing captions near the current position…";
    status(stage, stage !== lastStage); lastStage = stage;
  }
}
async function poll() {
  if (!enabled || !session || busy || awaitingSeek) return;
  busy = true;
  const token = generation;
  const current = session;
  try {
    const snapshot = await rpc<Snapshot>("PUT", `/sessions/${current.session_id}/playback`, {
      client_seq: ++seq, seek_epoch: epoch, position_ms: Math.min(current.duration_ms,Math.max(0,Math.round(number("time-pos")*1000))),
      rate: number("speed", 1), audio_delay_ms: Math.round(number("audio-delay")*1000)});
    await consume(snapshot, token);
  } catch (e) {
    traceEvent("poll_error",{error:String(e),position:number("time-pos")});
    if (token === generation) {
      const code=String(e).replace(/^Error: /,"");
      if (["CLIENT_REQUIRED","NOT_FOUND","HELPER_DISCONNECTED"].includes(code)) {
        // Native modal panels can suspend JS timers long enough for a lease
        // to expire. Rebuild the session at the actual current playback point.
        status("Reconnecting to the local subtitle engine…");
        await start();
      } else {enabled = false; showError(e);}
    }
  }
  finally { busy = false; }
}
function listen(name: string, fn: () => void) { events.push([name, iina.event.on(name, fn)]); }
function setting(key: string, value: string) {
  if (iina.preferences.get(key) === value) { syncSettings(); return; }
  iina.preferences.set(key, value); iina.preferences.sync();
  syncSettings();
  if (enabled) void start();
}
function setSubtitleSize(value: number, save: boolean) {
  const size = validSubtitleSize(value);
  if (size === undefined) return;
  if (save) { iina.preferences.set("subtitleSize", size); iina.preferences.sync(); syncSettings(); }
  const own = renderer.path && ownedTrack(tracks(), renderer.path);
  if (enabled && own && String(own.id) === iina.mpv.getString("sid")) {
    try { subtitleSize.apply(size); } catch (error) { traceEvent("size_error", {error:String(error)}); status("Could not change subtitle size; captions still work.", true); }
  }
}
function toggle(key: "pauseUntilReady" | "subtitleBox", value: boolean) {
  iina.preferences.set(key, value); iina.preferences.sync(); syncSettings();
  if (key === "subtitleBox") syncSubtitleAppearance();
  else if (value) { intent.reset(); if (enabled && session && !session.ready) hold(); }
  else intent.userPlay();
}
function menu(title: string, action: () => void) { iina.menu.addItem(iina.menu.item(title, action)); }

menu("Enable AI subtitles for this video", () => { void start(); });
menu("Show subtitle status", () => {setupSidebar(); iina.sidebar.show(); status(latestStatus);});
menu("Stop AI subtitles", () => { void stop(); status("AI subtitles stopped; playback remains under your control.", true); });
menu("Play / continue", () => { intent.userPlay(); iina.mpv.set("pause", false); });
menu("Retry at current position", () => { void start(); });
for (const [label, target] of [["Original language", "original"], ["Traditional Chinese", "zh-TW"], ["Simplified Chinese", "zh-CN"], ["English", "en"], ["Japanese", "ja"], ["Korean", "ko"]]) menu(`Output: ${label}`, () => setting("target", target));
for (const [label, source] of [["Auto-detect", "auto"], ["English", "en"], ["Japanese", "ja"], ["Chinese", "zh"], ["Korean", "ko"]]) menu(`Source language: ${label}`, () => setting("source", source));
menu("Prioritize this window", () => { if (session) void rpc("POST", `/sessions/${session.session_id}/actions`, {action: "prioritize"}).catch(showError); });
menu("Export generated subtitles…", () => {
  if (!session) return status("Enable AI subtitles first.", true);
  const output = iina.utils.prompt("Enter an absolute SRT export path. Existing files are not overwritten; incomplete exports are marked partial.");
  if (output) void rpc("POST", `/sessions/${session.session_id}/export`, {output}).then(() => status("Subtitles exported.", true)).catch(showError);
});
menu("Diagnostics: player and audio track", () => {
  const data = {mpv: iina.mpv.getString("mpv-version"), audio: tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected,codec:t.codec})), paused: paused()};
  iina.console.log(JSON.stringify(data)); status(JSON.stringify(data), true);
});
menu("Diagnostics: 100 subtitle reloads (test media)", () => {
  void stop().then(rendererSmoke).catch(showError);
});

function setupSidebar() {
  if (sidebarLoaded) return;
  // IINA throws when loadFile runs before its native window exists. Defer to
  // window-loaded or a user action; never abort timer/event registration.
  iina.sidebar.loadFile("sidebar.html");
  sidebarLoaded = true;
  iina.sidebar.onMessage("ready", () => { status(latestStatus); syncSettings(); });
  iina.sidebar.onMessage("action", (data: {action: string; target?: string; value?: boolean | number}) => {
    if (data.action === "play") {intent.userPlay(); iina.mpv.set("pause", false);}
    else if (data.action === "retry") void start();
    else if (data.action === "stop") void stop().then(() => status("AI subtitles stopped; playback remains under your control."));
    else if (data.action === "set-target" && data.target && targets.has(data.target)) setting("target", data.target);
    else if (data.action === "set-pause-until-ready" && typeof data.value === "boolean") toggle("pauseUntilReady", data.value);
    else if (data.action === "set-subtitle-box" && typeof data.value === "boolean") toggle("subtitleBox", data.value);
    else if (data.action === "preview-subtitle-size" && typeof data.value === "number") setSubtitleSize(data.value, false);
    else if (data.action === "set-subtitle-size" && typeof data.value === "number") setSubtitleSize(data.value, true);
    else if (data.action === "diagnostic") {
      const report = {at:new Date().toISOString(),status:latestStatus,enabled,epoch,renderer_revision:renderer.installed,
        selected_sid:iina.mpv.getString("sid"),paused:paused(),mpv:iina.mpv.getString("mpv-version"),
        prepared_ranges:session?.prepared_ranges,installed_ranges:session?.installed_ranges,ready:session?.ready,
        metrics:session?.metrics,error:session?.error,events:trace,audio:tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected}))};
      iina.file.write("@data/cue-session-diagnostic.json",JSON.stringify(report,null,2));
      iina.core.osd("Cue diagnostics saved without media paths, subtitle text, or credentials.");
    }
  });
}
listen("iina.window-loaded", setupSidebar);
listen("mpv.pause.changed", () => { if (!paused()) intent.userPlay(); });
listen("mpv.seek", () => {
  traceEvent("seek",{enabled,position:number("time-pos")});
  if (!enabled) return;
  epoch++; renderer.installed = 0; awaitingSeek = true; intent.reset(); hold();
  if (seekTimer) clearTimeout(seekTimer);
  seekTimer = setTimeout(() => {awaitingSeek = false; void poll();}, 300);
});
listen("mpv.aid.changed", () => { traceEvent("audio_changed",{enabled}); if (enabled) void start(); });
listen("mpv.audio-delay.changed", () => { if (enabled && number("audio-delay") !== 0) { void stop(); showError("AUDIO_DELAY_UNSUPPORTED"); } });
listen("mpv.sid.changed", () => {
  if (!enabled || !selected || renderer.changing || !renderer.path) return;
  const own = ownedTrack(tracks(), renderer.path);
  if (!own || String(own.id) !== iina.mpv.getString("sid")) { void stop(); status("Your subtitle selection was kept; Cue stopped preparing captions.", true); }
});
listen("mpv.end-file", () => { void stop(); });
listen("iina.file-loaded", () => {
  void stop().then(() => {
    if (iina.preferences.get("autoEnable") && !tracks().some(t=>t.type==="sub"&&t.selected) && !targetSubtitleExists(tracks(),iina.preferences.get("target"))) void start();
  });
});
const timer = setInterval(() => {void poll();}, 500);
listen("iina.window-will-close", () => {
  void stop(); clearInterval(timer); if (seekTimer) clearTimeout(seekTimer);
  for (const [name, id] of events) iina.event.off(name, id);
  setTimeout(disposeClient, 1000);
});
