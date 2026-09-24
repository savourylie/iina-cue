import {t} from "./strings";
import type {Artifact, Track} from "./types";
import {ownedTrack} from "./control";
export const tracks = (): Track[] => iina.mpv.getNative("track-list") || [];
export const number = (name: string, fallback = 0): number => {
  const value = iina.mpv.getNumber(name); return Number.isFinite(value) ? value : fallback;
};
export const paused = (): boolean => !!iina.mpv.getFlag("pause");
export function mediaSnapshot() {
  const path = iina.mpv.getString("path");
  if (!path || !path.startsWith("/")) throw new Error("MEDIA_UNSUPPORTED");
  const track = tracks().find(t => t.type === "audio" && t.selected);
  if (!track) throw new Error("NO_AUDIO_TRACK");
  if (track.external) throw new Error("MEDIA_UNSUPPORTED");
  if (number("audio-delay") !== 0) throw new Error("AUDIO_DELAY_UNSUPPORTED");
  return {path, position_ms: Math.max(0, Math.round(number("time-pos")*1000)),
    track: {mpv_id: track.id, ff_index: track["ff-index"], language: track.lang, title: track.title,
      codec: track.codec, channels: track["demux-channel-count"], external: track.external}};
}
export class SubtitleRenderer {
  path?: string;
  installed = 0;
  changing = false;
  async install(artifact: Artifact, firstSelection: boolean, stillCurrent: () => boolean): Promise<void> {
    if (!stillCurrent()) throw new Error("STALE_ACK");
    if (!artifact.path.startsWith("/") || !iina.file.exists(artifact.path)) throw new Error("SUBTITLE_INSTALL_FAILED");
    if (!artifact.cue_count) { this.installed = artifact.revision; return; }
    const track = ownedTrack(tracks(), artifact.path);
    const sid = iina.mpv.getString("sid");
    const select = firstSelection || (track && String(track.id) === sid);
    if (!firstSelection && (!track || !select)) throw new Error("USER_SUBTITLE_SELECTION");
    this.changing = true;
    this.path = artifact.path;
    try {
      if (track) iina.mpv.command("sub-reload", [String(track.id)]);
      else iina.mpv.command("sub-add", [artifact.path, select ? "select" : "auto", t("track.title"), ""]);
      const until = Date.now()+3000;
      while (Date.now() < until) {
        await new Promise<void>(resolve => setTimeout(resolve, 100));
        if (!stillCurrent()) throw new Error("STALE_ACK");
        const current = ownedTrack(tracks(), artifact.path);
        if (current) {
          // Never set sid after an asynchronous reload: the user may have
          // disabled or changed subtitles while the command was in flight.
          if (select && iina.mpv.getString("sid") !== String(current.id)) throw new Error("USER_SUBTITLE_SELECTION");
          this.installed = artifact.revision;
          return;
        }
      }
      throw new Error("SUBTITLE_INSTALL_FAILED");
    } finally { this.changing = false; }
  }
  remove() {
    this.changing = true;
    try {
      if (this.path) { const track = ownedTrack(tracks(), this.path); if (track) iina.mpv.command("sub-remove", [String(track.id)]); }
      this.path = undefined; this.installed = 0;
    } finally { this.changing = false; }
  }
}
