import {rpc, disposeClient} from "./client";
import {type PreflightFacts} from "./install-runtime";
import {installPublishedRuntime, MODEL_BYTES, openCreditLink, readMacFacts, RUNTIME_ARCHIVE_BYTES, RUNTIME_MINIMUM_MACOS} from "./runtime-install";
import {createSetupController} from "./setup-controller";
import {acceptSnapshot, actionErrorStatus, coverageStrip, errorStatus, holeAt, languageName, offStatus, originalLanguageChoice, ownedTrack, partialFailureStatus, PlaybackIntent, preparationStatus, readyStatus, remuxFilename, statusText, targetSubtitleExists} from "./control";
import type {CueStatus} from "./control";
import {has, sidebarStrings, t} from "./strings";
import type {StringKey} from "./strings";
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
let latestStatus: CueStatus = offStatus();
type RemuxStatus = {text: string; state: "idle" | "running" | "complete" | "error" | "cancelled"; progressPct?: number | null; cancellable?: boolean};
let remuxStatus: RemuxStatus = {text: "", state: "idle"};
let remuxJobId: string | undefined;
let remuxPolling = false;
let remuxCancelling = false;
let remuxStarting = false;
let remuxDraft: {source: string; folder: string; suggested: string; error?: string} | undefined;
// Show in Finder only ever reveals files Cue itself wrote, never a path sent by the page.
const revealable: {remux?: string; export?: string} = {};
let lastStage = "";
let seekTimer: ReturnType<typeof setTimeout> | undefined;
let awaitingSeek = false;
let sidebarLoaded = false;
let lifecycle = 0;
const events: [string, string][] = [];
const trace: object[] = [];
const targets = new Set(["original", "zh-TW", "zh-CN", "en", "ja", "ko"]);
const experimental = (code: string) => t("lang.experimentalName", {name: languageName(code)});
const sourceChoices = [[t("lang.auto"), "auto"], ...["en", "ja", "zh", "ko"].map(code => [languageName(code), code]),
  ...["yue", "fr", "de", "it", "pt", "ru", "es"].map(code => [experimental(code), code])];
const sources = new Set(sourceChoices.map(([, code]) => code));
function target() {
  const value = iina.preferences.get("target");
  return targets.has(value) ? value : "original";
}
function syncSettings() {
  const detected = session?.language?.code;
  const manual = iina.preferences.get("source");
  const source = sources.has(manual) ? manual : "auto";
  const originalCode = source !== "auto" ? source : detected && detected !== "und" ? detected : undefined;
  const original = originalLanguageChoice(originalCode, source === "auto" ? session?.language?.status : "manual",
    {active: enabled && !!session, unclear: !!session?.skipped_language_ranges?.length});
  if (sidebarLoaded) iina.sidebar.postMessage("cue-settings", {
    target: target(), source, pauseUntilReady: iina.preferences.get("pauseUntilReady") === true,
    subtitleBox: iina.preferences.get("subtitleBox") === true,
    subtitleSize: validSubtitleSize(iina.preferences.get("subtitleSize")) ?? subtitleSize.current(),
    originalLabel: original.label, originalHint: original.hint
  });
}
function traceEvent(event: string, data: object = {}) {
  trace.push({event,at:Date.now(),generation,epoch,...data});
  if (trace.length>32) trace.shift();
}
function status(next: CueStatus, osd = false) {
  const changed = JSON.stringify(latestStatus) !== JSON.stringify(next);
  latestStatus = next;
  if (sidebarLoaded) iina.sidebar.postMessage("cue-status", {...next, enabled});
  if (osd && changed) iina.core.osd(statusText(next));
}
function refreshStatus() { status(latestStatus); }
function setRemuxStatus(update: RemuxStatus, osd = false) {
  remuxStatus = update;
  if (sidebarLoaded) {try {iina.sidebar.postMessage("cue-remux-status", update);} catch {}}
  if (osd) {try {iina.core.osd(update.text);} catch {}}
}
function syncRemuxDraft() {
  if (sidebarLoaded) iina.sidebar.postMessage("cue-remux-draft", remuxDraft
    ? {active:true, folder:remuxDraft.folder, suggested:remuxDraft.suggested, error:remuxDraft.error ?? ""}
    : {active:false});
}
function showError(e: unknown) {
  const code = String(e).replace(/^Error: /, "");
  const language = session?.language?.code && session.language.code !== "und" ? languageName(session.language.code) : undefined;
  status(errorStatus(code, language), true);
  syncSettings();
}
function showActionError(e: unknown) {
  const code = String(e).replace(/^Error: /, "");
  status(actionErrorStatus(code), true);
}
function hold() {
  if (iina.preferences.get("pauseUntilReady") === true && intent.hold(paused())) iina.mpv.set("pause", true);
}
function syncSubtitleAppearance() {
  const own = renderer.path && ownedTrack(tracks(), renderer.path);
  if (enabled && own && String(own.id) === iina.mpv.getString("sid")) {
    if (iina.preferences.get("subtitleBox") === true) {
      try { subtitleStyle.enable(); } catch (error) { traceEvent("style_error", {error:String(error)}); status({tone:"warning", title:t("status.backgroundFailed"), detail:t("status.captionsStillWork")}, true); }
    } else subtitleStyle.restore();
    const size = validSubtitleSize(iina.preferences.get("subtitleSize"));
    if (size !== undefined) {
      try { subtitleSize.apply(size); } catch (error) { traceEvent("size_error", {error:String(error)}); status({tone:"warning", title:t("status.sizeFailed"), detail:t("status.captionsStillWork")}, true); }
    } else subtitleSize.restore();
  } else { subtitleStyle.restore(); subtitleSize.restore(); }
}
async function stop(forRestart = false) {
  const previous = session;
  generation++; enabled = false; session = undefined; epoch = 0; seq = 0; selected = false;
  intent.reset(); subtitleStyle.restore(); subtitleSize.restore(); renderer.remove(); syncSettings();
  if (seekTimer) clearTimeout(seekTimer);
  awaitingSeek = false;
  if (!forRestart) status(offStatus());
  if (previous) { try { await rpc("DELETE", `/sessions/${previous.session_id}`); } catch {} }
}
async function start() {
  traceEvent("start",{position:number("time-pos")});
  setupSidebar();
  const requestedGeneration = generation + 1;
  await stop(true);
  if (generation !== requestedGeneration) return;
  const token = generation;
  try {
    const media = mediaSnapshot();
    enabled = true; hold(); status({tone:"working", title:t("status.starting"), detail:t("status.startingDetail")}, true);
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
  const languageKey = (s: Snapshot) => `${s.language?.code}|${s.language?.status}|${!!s.skipped_language_ranges?.length}`;
  const priorLanguage = languageKey(session);
  session = snapshot;
  if (languageKey(snapshot) !== priorLanguage) syncSettings();
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
    if (session.ready) status(partialFailureStatus(session.buffer_wall_ms), true);
    else showError(snapshot.error.code);
    return;
  }
  const hole = holeAt(session, Math.round(number("time-pos")*1000));
  if (hole) {
    // Nothing is being prepared here, so playback is never held for it.
    if (session.ready) intent.ready();
    status({...hole, coverage: coverage(session)}, lastStage !== hole.title); lastStage = hole.title;
    return;
  }
  if (session.ready) {
    const wasHolding = intent.holding;
    intent.ready();
    status({...readyStatus(session.buffer_wall_ms, paused(), wasHolding), coverage: coverage(session)}, wasHolding);
  } else {
    if (session.buffer_wall_ms <= 1000) hold();
    const stage = {...preparationStatus(session), coverage: coverage(session)};
    status(stage, session.stage !== lastStage); lastStage = session.stage;
  }
}
function coverage(s: Snapshot) {
  return coverageStrip(s.prepared_ranges ?? [], s.installed_ranges ?? [], Math.max(0, Math.round(number("time-pos")*1000)));
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
        status({tone:"working", title:t("status.reconnecting"), detail:t("status.reconnectingDetail")});
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
    try { subtitleSize.apply(size); } catch (error) { traceEvent("size_error", {error:String(error)}); status({tone:"warning", title:t("status.sizeFailed"), detail:t("status.captionsStillWork")}, true); }
  }
}
function toggle(key: "pauseUntilReady" | "subtitleBox", value: boolean) {
  iina.preferences.set(key, value); iina.preferences.sync(); syncSettings();
  if (key === "subtitleBox") syncSubtitleAppearance();
  else if (value) { intent.reset(); if (enabled && session && !session.ready) hold(); }
  else intent.userPlay();
}
function menu(title: string, action: () => void) { iina.menu.addItem(iina.menu.item(title, action)); }
function advancedItem(title: string, action: () => void) { advanced.addSubMenuItem(iina.menu.item(title, action)); }
const advanced = iina.menu.item(t("menu.advanced"));

async function exportSubtitles() {
  const active = session;
  const token = generation;
  if (!active || !active.artifact?.cue_count) return status({tone:"warning", title:t("status.nothingToExport"), detail:t("status.nothingToExportDetail")}, true);
  let output: string | undefined;
  try { output = await iina.utils.prompt(t("export.prompt")); }
  catch { return; }
  if (!output || token !== generation || session?.session_id !== active.session_id) return;
  try {
    const result = await rpc<{path: string}>("POST", `/sessions/${active.session_id}/export`, {output});
    if (token === generation) { revealable.export = result.path; status({tone:"info", title:t("status.exported"), detail:result.path, reveal:true}, true); }
  } catch (error) { if (token === generation) showActionError(error); }
}
async function remuxCurrentMedia() {
  if (remuxJobId || remuxStarting) { iina.core.osd(t("remux.busy")); return; }
  const source = iina.mpv.getString("path");
  if (!source || !source.startsWith("/")) return setRemuxStatus({text:t("remux.noLocalVideo"),state:"error"}, true);
  const slash = source.lastIndexOf("/");
  const dot = source.lastIndexOf(".");
  const suggested = `${dot > slash ? source.slice(slash + 1, dot) : source.slice(slash + 1)}.cue-remux.mkv`;
  remuxStarting = true;
  try {
    const folder = await iina.utils.chooseFile(t("remux.chooseFolder"), {chooseDir:true});
    if (!folder) return;
    if (iina.mpv.getString("path") !== source) return setRemuxStatus({text:t("remux.videoChanged"),state:"error"}, true);
    remuxDraft = {source, folder, suggested};
    try { setupSidebar(); iina.sidebar.show(); } catch {}
    if (remuxStatus.state === "error" || remuxStatus.state === "cancelled") setRemuxStatus({text:"",state:"idle"});
    syncRemuxDraft();
  } catch (error) { setRemuxStatus({text:t("remux.couldNotStart", {reason:String(error).replace(/^Error: /, "")}),state:"error"}, true); }
  finally {remuxStarting = false;}
}
async function confirmRemux(response: string) {
  const draft = remuxDraft;
  if (!draft || remuxJobId || remuxStarting) return;
  const {source, folder, suggested} = draft;
  if (iina.mpv.getString("path") !== source) {
    remuxDraft = undefined; syncRemuxDraft();
    return setRemuxStatus({text:t("remux.videoChanged"),state:"error"}, true);
  }
  const checked = remuxFilename(response, suggested, folder, path => iina.file.exists(path));
  if (checked.error || !checked.output) { remuxDraft = {...draft, error: checked.error}; syncRemuxDraft(); return; }
  const output = checked.output;
  remuxStarting = true;
  remuxDraft = undefined; syncRemuxDraft();
  setRemuxStatus({text:t("remux.preparing"),state:"running"});
  try {
    const result = await rpc<{job_id: string}>("POST", "/remux", {source, output});
    remuxJobId = result.job_id;
    setRemuxStatus({text:t("remux.copying"),state:"running",cancellable:true});
  } catch (error) {
    if (iina.mpv.getString("path") === source) {remuxDraft = draft; syncRemuxDraft();}
    setRemuxStatus({text:t("remux.couldNotStart", {reason:String(error).replace(/^Error: /, "")}),state:"error"}, true);
  } finally {remuxStarting = false;}
}
async function cancelRemuxJob() {
  const id = remuxJobId;
  if (!id || remuxCancelling) return;
  remuxCancelling = true;
  setRemuxStatus({...remuxStatus, text:t("remux.cancelling"), cancellable:false});
  try { await rpc("POST", `/remux/${id}/cancel`, {}); }
  catch (error) { remuxCancelling = false; showActionError(error); }
}
async function pollRemux() {
  if (!remuxJobId || remuxPolling) return;
  remuxPolling = true;
  const id = remuxJobId;
  try {
    const job = await rpc<{state: string; phase?: string; progress_pct?: number | null; path?: string; error?: {code: string}}>("GET", `/remux/${id}`);
    if (remuxJobId !== id) return;
    if (job.state === "running") {
      const text = t(remuxCancelling && job.phase !== "saving" ? "remux.cancelling"
        : job.phase === "verifying" ? "remux.verifying"
        : job.phase === "saving" ? "remux.saving"
        : job.phase === "copying" ? "remux.copying" : "remux.preparing");
      // Once saving starts the helper commits the file, so cancelling is no longer offered.
      setRemuxStatus({text,state:"running",progressPct:job.progress_pct,cancellable:!remuxCancelling && job.phase !== "saving"});
    }
    else {
      remuxJobId = undefined; remuxCancelling = false;
      if (job.state === "cancelled") setRemuxStatus({text:t("remux.cancelled"),state:"cancelled"}, true);
      else if (job.state === "complete") { revealable.remux = job.path; setRemuxStatus({text:t("remux.saved", {path:job.path ?? ""}),state:"complete",progressPct:100}, true); }
      else {
        const key = `remux.failed.${job.error?.code}`;
        setRemuxStatus({text:t(has(key) ? key : "remux.failed.unknown"),state:"error"}, true);
      }
    }
  } catch (error) {
    if (remuxJobId === id) {remuxJobId = undefined; remuxCancelling = false; setRemuxStatus({text:t("remux.statusUnavailable", {reason:String(error).replace(/^Error: /, "")}),state:"error"}, true);}
  } finally {remuxPolling = false;}
}
function saveDiagnostics() {
  const report = {at:new Date().toISOString(),status:latestStatus,enabled,epoch,renderer_revision:renderer.installed,
    selected_sid:iina.mpv.getString("sid"),paused:paused(),mpv:iina.mpv.getString("mpv-version"),
    prepared_ranges:session?.prepared_ranges,installed_ranges:session?.installed_ranges,ready:session?.ready,
    metrics:session?.metrics,error:session?.error,events:trace,audio:tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected}))};
  iina.file.write("@data/cue-session-diagnostic.json",JSON.stringify(report,null,2));
  iina.core.osd(t("diagnostics.saved"));
}
function playerAudioDiagnostics() {
  const data = {mpv: iina.mpv.getString("mpv-version"), audio: tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected,codec:t.codec})), paused: paused()};
  iina.console.log(JSON.stringify(data)); status({tone:"info", title:t("status.playerDiagnostic"), detail:JSON.stringify(data)}, true);
}
function reloadDiagnostics() { void stop().then(rendererSmoke).catch(showActionError); }

advancedItem(t("menu.remux"), () => { void remuxCurrentMedia(); });
advancedItem(t("menu.export"), () => { void exportSubtitles(); });
advancedItem(t("menu.saveDiagnostics"), saveDiagnostics);
advancedItem(t("menu.playerDiagnostic"), playerAudioDiagnostics);
advancedItem(t("menu.reloadDiagnostic"), reloadDiagnostics);

menu(t("menu.openSidebar"), () => {setupSidebar(); iina.sidebar.show(); refreshStatus();});
iina.menu.addItem(advanced);
for (const target of ["original", "zh-TW", "zh-CN", "en", "ja", "ko"]) menu(t("menu.output", {label: t(`lang.${target}` as StringKey)}), () => setting("target", target));
for (const [label, source] of sourceChoices) menu(t("menu.source", {label}), () => setting("source", source));
menu(t("menu.prioritize"), () => { if (session) void rpc("POST", `/sessions/${session.session_id}/actions`, {action: "prioritize"}).catch(showActionError); });

const resolveSupportPath = (path: string) => {
  const utils = iina.utils as {resolvePath?: (path: string) => string | null | undefined};
  return typeof utils.resolvePath === "function" ? utils.resolvePath(path) : null;
};
const setupController = createSetupController({
  rpc: (method, path, body) => rpc(method, path, body ?? {}),
  post: (view) => iina.sidebar.postMessage("cue-setup", view),
  facts: async (): Promise<PreflightFacts> => {
    const core = iina.core as {getVersion?: () => {iina?: string}};
    // IINA 1.4 is the oldest host this plugin loads in; an unreadable version is treated as that.
    const version = typeof core.getVersion === "function" ? core.getVersion()?.iina : undefined;
    return {
      ...(await readMacFacts({resolve: resolveSupportPath, exec: (file, args) => iina.utils.exec(file, args)})),
      iina: version && /^\d+(\.\d+)*/.test(version) ? version.match(/^\d+(\.\d+)*/)![0] : "1.4.0",
      minimumMacos: RUNTIME_MINIMUM_MACOS,
      bytesNeeded: RUNTIME_ARCHIVE_BYTES + MODEL_BYTES,
    };
  },
  installRuntime: (onProgress, onUnpack) => installPublishedRuntime({
    onProgress,
    onUnpack,
    wait: (ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
    resolve: resolveSupportPath,
    exec: (file, args) => iina.utils.exec(file, args),
    remuxActive: remuxStatus.state === "running",
    sessions: session ? 1 : 0,
  }),
  wait: (ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
});

function setupSidebar() {
  if (sidebarLoaded) return;
  // IINA throws when loadFile runs before its native window exists. Defer to
  // window-loaded or a user action; never abort timer/event registration.
  iina.sidebar.loadFile("sidebar.html");
  sidebarLoaded = true;
  iina.sidebar.onMessage("ready", () => { iina.sidebar.postMessage("cue-strings", sidebarStrings()); void setupController.refresh(); refreshStatus(); setRemuxStatus(remuxStatus); syncRemuxDraft(); syncSettings(); });
  iina.sidebar.onMessage("start-setup", () => { void setupController.start(); });
  iina.sidebar.onMessage("open-link", (data: {link?: unknown}) => { openCreditLink(data?.link, (file, args) => iina.utils.exec(file, args)); });
  iina.sidebar.onMessage("action", (data: {action: string; target?: string; value?: boolean | number; filename?: string}) => {
    if (data.action === "set-enabled" && typeof data.value === "boolean") {
      if (data.value && !enabled) void start();
      else if (!data.value) void stop();
    }
    else if (data.action === "retry") void start();
    else if (data.action === "set-target" && data.target && targets.has(data.target)) setting("target", data.target);
    else if (data.action === "set-source" && data.target && sources.has(data.target)) setting("source", data.target);
    else if (data.action === "set-pause-until-ready" && typeof data.value === "boolean") toggle("pauseUntilReady", data.value);
    else if (data.action === "set-subtitle-box" && typeof data.value === "boolean") toggle("subtitleBox", data.value);
    else if (data.action === "preview-subtitle-size" && typeof data.value === "number") setSubtitleSize(data.value, false);
    else if (data.action === "set-subtitle-size" && typeof data.value === "number") setSubtitleSize(data.value, true);
    else if (data.action === "remux") void remuxCurrentMedia();
    else if (data.action === "confirm-remux" && typeof data.filename === "string") void confirmRemux(data.filename);
    else if (data.action === "check-remux-name" && typeof data.filename === "string" && remuxDraft) {
      const error = remuxFilename(data.filename, remuxDraft.suggested, remuxDraft.folder, path => iina.file.exists(path)).error;
      if (error !== remuxDraft.error) { remuxDraft = {...remuxDraft, error}; syncRemuxDraft(); }
    }
    else if ((data.action === "reveal-remux" || data.action === "reveal-export")) {
      const path = data.action === "reveal-remux" ? revealable.remux : revealable.export;
      if (path && iina.file.exists(path)) void iina.utils.exec("/usr/bin/open", ["-R", path]).catch(showActionError);
    }
    else if (data.action === "stop-remux") void cancelRemuxJob();
    else if (data.action === "cancel-remux") {
      remuxDraft = undefined; syncRemuxDraft();
      if (remuxStatus.state === "error" || remuxStatus.state === "cancelled") setRemuxStatus({text:"",state:"idle"});
    }
    else if (data.action === "export") void exportSubtitles();
    else if (data.action === "diagnostic") saveDiagnostics();
    else if (data.action === "player-diagnostic") playerAudioDiagnostics();
    else if (data.action === "reload-diagnostic") reloadDiagnostics();
  });
}
listen("iina.window-loaded", () => { lifecycle++; setupSidebar(); });
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
  if (!own || String(own.id) !== iina.mpv.getString("sid")) { void stop(); status({tone:"info", title:t("status.stopped"), detail:t("status.selectionKept")}, true); }
});
listen("mpv.end-file", () => { remuxDraft = undefined; syncRemuxDraft(); void stop(); });
listen("iina.file-loaded", () => {
  remuxDraft = undefined; syncRemuxDraft();
  const reset = stop();
  const token = generation;
  void reset.then(() => {
    if (generation !== token) return;
    if (iina.preferences.get("autoEnable") && !tracks().some(t=>t.type==="sub"&&t.selected) && !targetSubtitleExists(tracks(),iina.preferences.get("target"))) void start();
  });
});
const timer = setInterval(() => {void poll(); void pollRemux();}, 500);
listen("iina.window-will-close", () => {
  remuxDraft = undefined; syncRemuxDraft();
  // The JS context outlives player windows, so keep the poll timer and event
  // listeners: reopening a video must just work. Drop only the session and,
  // when no newer window exists, the helper lease; the next start()
  // reconnects on demand. Server-side leases remain the crash fallback.
  const token = lifecycle;
  const release = () => { if (token === lifecycle) disposeClient(); };
  lastStage = "";
  setTimeout(release, 1000);
  void stop().then(release, release);
});
