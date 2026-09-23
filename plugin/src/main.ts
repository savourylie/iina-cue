import {rpc, disposeClient} from "./client";
import {acceptSnapshot, actionErrorStatus, errorStatus, OFF_STATUS, originalLanguageChoice, originalLanguageLabel, ownedTrack, partialFailureStatus, PlaybackIntent, preparationStatus, readyStatus, statusText, targetSubtitleExists} from "./control";
import type {CueStatus} from "./control";
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
let latestStatus: CueStatus = OFF_STATUS;
type RemuxStatus = {text: string; state: "idle" | "running" | "complete" | "error"; progressPct?: number | null};
let remuxStatus: RemuxStatus = {text: "", state: "idle"};
let remuxJobId: string | undefined;
let remuxPolling = false;
let remuxStarting = false;
let remuxDraft: {source: string; folder: string; suggested: string} | undefined;
let lastStage = "";
let seekTimer: ReturnType<typeof setTimeout> | undefined;
let awaitingSeek = false;
let sidebarLoaded = false;
let lifecycle = 0;
const events: [string, string][] = [];
const trace: object[] = [];
const targets = new Set(["original", "zh-TW", "zh-CN", "en", "ja", "ko"]);
const sourceChoices = [["Auto-detect", "auto"], ["English", "en"], ["Japanese", "ja"],
  ["Chinese", "zh"], ["Korean", "ko"], ["Cantonese (experimental)", "yue"],
  ["French (experimental)", "fr"], ["German (experimental)", "de"],
  ["Italian (experimental)", "it"], ["Portuguese (experimental)", "pt"],
  ["Russian (experimental)", "ru"], ["Spanish (experimental)", "es"]];
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
    ? {active:true, folder:remuxDraft.folder, suggested:remuxDraft.suggested}
    : {active:false});
}
function showError(e: unknown) {
  const code = String(e).replace(/^Error: /, "");
  const language = session?.language?.code && session.language.code !== "und" ? originalLanguageLabel(session.language.code).replace(" (original)", "") : undefined;
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
      try { subtitleStyle.enable(); } catch (error) { traceEvent("style_error", {error:String(error)}); status({tone:"warning", title:"Background not applied", detail:"Captions still work."}, true); }
    } else subtitleStyle.restore();
    const size = validSubtitleSize(iina.preferences.get("subtitleSize"));
    if (size !== undefined) {
      try { subtitleSize.apply(size); } catch (error) { traceEvent("size_error", {error:String(error)}); status({tone:"warning", title:"Size not changed", detail:"Captions still work."}, true); }
    } else subtitleSize.restore();
  } else { subtitleStyle.restore(); subtitleSize.restore(); }
}
async function stop(forRestart = false) {
  const previous = session;
  generation++; enabled = false; session = undefined; epoch = 0; seq = 0; selected = false;
  intent.reset(); subtitleStyle.restore(); subtitleSize.restore(); renderer.remove(); syncSettings();
  if (seekTimer) clearTimeout(seekTimer);
  awaitingSeek = false;
  if (!forRestart) status(OFF_STATUS);
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
    enabled = true; hold(); status({tone:"working", title:"Starting", detail:"Loading the local subtitle engine…"}, true);
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
  if (session.ready) {
    const wasHolding = intent.holding;
    intent.ready();
    status(readyStatus(session.buffer_wall_ms, paused(), wasHolding), wasHolding);
  } else {
    if (session.buffer_wall_ms <= 1000) hold();
    const stage = preparationStatus(session);
    status(stage, session.stage !== lastStage); lastStage = session.stage;
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
        status({tone:"working", title:"Reconnecting", detail:"Reconnecting to the local subtitle engine…"});
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
    try { subtitleSize.apply(size); } catch (error) { traceEvent("size_error", {error:String(error)}); status({tone:"warning", title:"Size not changed", detail:"Captions still work."}, true); }
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
const advanced = iina.menu.item("Advanced");

async function exportSubtitles() {
  const active = session;
  const token = generation;
  if (!active || !active.artifact?.cue_count) return status({tone:"warning", title:"Nothing to export yet", detail:"Cue has not generated captions for this video."}, true);
  let output: string | undefined;
  try { output = await iina.utils.prompt("Enter an absolute SRT export path. Existing files are not overwritten; incomplete exports are marked partial."); }
  catch { return; }
  if (!output || token !== generation || session?.session_id !== active.session_id) return;
  try {
    const result = await rpc<{path: string}>("POST", `/sessions/${active.session_id}/export`, {output});
    if (token === generation) status({tone:"info", title:"Subtitles exported", detail:result.path}, true);
  } catch (error) { if (token === generation) showActionError(error); }
}
async function remuxCurrentMedia() {
  if (remuxJobId || remuxStarting) { iina.core.osd("A remux is already running."); return; }
  const source = iina.mpv.getString("path");
  if (!source || !source.startsWith("/")) return setRemuxStatus({text:"Open a local video before remuxing.",state:"error"}, true);
  const slash = source.lastIndexOf("/");
  const dot = source.lastIndexOf(".");
  const suggested = `${dot > slash ? source.slice(slash + 1, dot) : source.slice(slash + 1)}.cue-remux.mkv`;
  remuxStarting = true;
  try {
    const folder = await iina.utils.chooseFile("Choose a folder for the remuxed copy", {chooseDir:true});
    if (!folder) return;
    if (iina.mpv.getString("path") !== source) return setRemuxStatus({text:"The open video changed. Select Remux again for the current video.",state:"error"}, true);
    remuxDraft = {source, folder, suggested};
    try { setupSidebar(); iina.sidebar.show(); } catch {}
    if (remuxStatus.state === "error") setRemuxStatus({text:"",state:"idle"});
    syncRemuxDraft();
  } catch (error) { setRemuxStatus({text:`Remux could not start (${String(error).replace(/^Error: /, "")}).`,state:"error"}, true); }
  finally {remuxStarting = false;}
}
async function confirmRemux(response: string) {
  const draft = remuxDraft;
  if (!draft || remuxJobId || remuxStarting) return;
  const {source, folder, suggested} = draft;
  if (iina.mpv.getString("path") !== source) {
    remuxDraft = undefined; syncRemuxDraft();
    return setRemuxStatus({text:"The open video changed. Select Remux again for the current video.",state:"error"}, true);
  }
  const name = (response.trim() || suggested).replace(/\.(mp4|mov|m4v|webm|ts)$/i, ".mkv");
  const filename = name.toLowerCase().endsWith(".mkv") ? name : `${name}.mkv`;
  if (name === "." || name === ".." || name.startsWith(".") || name.endsWith(".") || filename.length > 240 || /[/\\\u0000-\u001f]/.test(name)) {
    return setRemuxStatus({text:"Choose a plain filename ending in .mkv (or omit the extension).",state:"error"}, true);
  }
  const output = `${folder.replace(/\/+$/, "")}/${filename}`;
  if (iina.file.exists(output)) return setRemuxStatus({text:"That output file already exists. Choose another name.",state:"error"}, true);
  remuxStarting = true;
  remuxDraft = undefined; syncRemuxDraft();
  setRemuxStatus({text:"Preparing remux…",state:"running"});
  try {
    const result = await rpc<{job_id: string}>("POST", "/remux", {source, output});
    remuxJobId = result.job_id;
    setRemuxStatus({text:"Copying streams…",state:"running"});
  } catch (error) {
    if (iina.mpv.getString("path") === source) {remuxDraft = draft; syncRemuxDraft();}
    setRemuxStatus({text:`Remux could not start (${String(error).replace(/^Error: /, "")}).`,state:"error"}, true);
  } finally {remuxStarting = false;}
}
async function pollRemux() {
  if (!remuxJobId || remuxPolling) return;
  remuxPolling = true;
  const id = remuxJobId;
  try {
    const job = await rpc<{state: string; phase?: string; progress_pct?: number | null; path?: string; error?: {code: string}}>("GET", `/remux/${id}`);
    if (remuxJobId !== id) return;
    if (job.state === "running") {
      const text = job.phase === "verifying" ? "Verifying timestamps and tracks…"
        : job.phase === "saving" ? "Saving the new video…"
        : job.phase === "copying" ? "Copying streams…" : "Preparing remux…";
      setRemuxStatus({text,state:"running",progressPct:job.progress_pct});
    }
    else {
      remuxJobId = undefined;
      if (job.state === "complete") setRemuxStatus({text:`Remux complete: ${job.path}`,state:"complete",progressPct:100}, true);
      else {
        const problem = ({REMUX_FAILED:"Could not copy this video's tracks into the new MKV.",
          REMUX_VERIFY_FAILED:"The new video's tracks or timestamps failed verification.",
          SOURCE_CHANGED:"The original video changed during copying. Retry when it is stable.",
          OUTPUT_EXISTS:"A file with this name appeared while copying. Choose another name."} as Record<string,string>)[job.error?.code || ""]
          || "Could not create the new video.";
        setRemuxStatus({text:`${problem} Original file is unchanged.`,state:"error"}, true);
      }
    }
  } catch (error) {
    if (remuxJobId === id) {remuxJobId = undefined; setRemuxStatus({text:`Remux status unavailable (${String(error).replace(/^Error: /, "")}). Check the output location.`,state:"error"}, true);}
  } finally {remuxPolling = false;}
}
function saveDiagnostics() {
  const report = {at:new Date().toISOString(),status:latestStatus,enabled,epoch,renderer_revision:renderer.installed,
    selected_sid:iina.mpv.getString("sid"),paused:paused(),mpv:iina.mpv.getString("mpv-version"),
    prepared_ranges:session?.prepared_ranges,installed_ranges:session?.installed_ranges,ready:session?.ready,
    metrics:session?.metrics,error:session?.error,events:trace,audio:tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected}))};
  iina.file.write("@data/cue-session-diagnostic.json",JSON.stringify(report,null,2));
  iina.core.osd("Cue diagnostics saved without media paths, subtitle text, or credentials.");
}
function playerAudioDiagnostics() {
  const data = {mpv: iina.mpv.getString("mpv-version"), audio: tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected,codec:t.codec})), paused: paused()};
  iina.console.log(JSON.stringify(data)); status({tone:"info", title:"Player and audio track", detail:JSON.stringify(data)}, true);
}
function reloadDiagnostics() { void stop().then(rendererSmoke).catch(showActionError); }

advancedItem("Remux current video (reset timestamps)…", () => { void remuxCurrentMedia(); });
advancedItem("Export generated subtitles…", () => { void exportSubtitles(); });
advancedItem("Save diagnostics", saveDiagnostics);
advancedItem("Diagnostics: player and audio track", playerAudioDiagnostics);
advancedItem("Diagnostics: 100 subtitle reloads (test media)", reloadDiagnostics);

menu("Open Cue sidebar", () => {setupSidebar(); iina.sidebar.show(); refreshStatus();});
iina.menu.addItem(advanced);
for (const [label, target] of [["Original language", "original"], ["Traditional Chinese", "zh-TW"], ["Simplified Chinese", "zh-CN"], ["English", "en"], ["Japanese", "ja"], ["Korean", "ko"]]) menu(`Output: ${label}`, () => setting("target", target));
for (const [label, source] of sourceChoices) menu(`Source language: ${label}`, () => setting("source", source));
menu("Prioritize this window", () => { if (session) void rpc("POST", `/sessions/${session.session_id}/actions`, {action: "prioritize"}).catch(showActionError); });

function setupSidebar() {
  if (sidebarLoaded) return;
  // IINA throws when loadFile runs before its native window exists. Defer to
  // window-loaded or a user action; never abort timer/event registration.
  iina.sidebar.loadFile("sidebar.html");
  sidebarLoaded = true;
  iina.sidebar.onMessage("ready", () => { refreshStatus(); setRemuxStatus(remuxStatus); syncRemuxDraft(); syncSettings(); });
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
    else if (data.action === "cancel-remux") {
      remuxDraft = undefined; syncRemuxDraft();
      if (remuxStatus.state === "error") setRemuxStatus({text:"",state:"idle"});
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
  if (!own || String(own.id) !== iina.mpv.getString("sid")) { void stop(); status({tone:"info", title:"Cue stopped", detail:"Your subtitle selection was kept."}, true); }
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
