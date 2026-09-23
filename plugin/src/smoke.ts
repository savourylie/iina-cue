import {SubtitleRenderer, number, tracks} from "./player";
import {ownedTrack} from "./control";

/** Explicit diagnostic: dummy captions, not generated subtitles or quality evidence. */
export async function rendererSmoke(): Promise<void> {
  const media = iina.mpv.getString("path");
  if (!media || !media.startsWith("/")) throw new Error("Open a local test video first.");
  const utils = iina.utils as IINA.API.Utils & {resolvePath(path: string): string};
  const file = "@data/cue-render-smoke.srt";
  const path = utils.resolvePath(file);
  const previous = iina.mpv.getString("sid");
  const renderer = new SubtitleRenderer();
  const before = tracks().filter(t=>t.type==="sub").length;
  const rows: object[] = [];
  const current = () => iina.mpv.getString("path") === media;
  const timestamp = (seconds: number) => {
    const ms = Math.round(seconds*1000), h = Math.floor(ms/3600000), m = Math.floor(ms/60000)%60, s = Math.floor(ms/1000)%60;
    return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")},${String(ms%1000).padStart(3,"0")}`;
  };
  try {
    for (let revision=1; revision<=100; revision++) {
      const start=number("time-pos");
      iina.file.write(file, `1\n${timestamp(start)} --> ${timestamp(start+10)}\nCue diagnostic caption ${revision} (not AI content)\n`);
      await renderer.install({path,revision,sha256:"diagnostic",cue_count:1,complete_movie:false},revision===1,current);
      const count=tracks().filter(t=>t.type==="sub").length;
      rows.push({revision,track_id:ownedTrack(tracks(),path)?.id,subtitle_tracks:count});
      if (count !== before+1) throw new Error("Unexpected subtitle track count");
    }
    const report = {status:"pass_track_presence_only",mpv:iina.mpv.getString("mpv-version"),rows,
      visual_flicker:"requires_manual_observation",audio:tracks().filter(t=>t.type==="audio").map(t=>({id:t.id,ff_index:t["ff-index"],selected:t.selected})),paused:iina.mpv.getFlag("pause")};
    iina.file.write("@data/cue-smoke-results.json",JSON.stringify(report,null,2));
    iina.core.osd("100 diagnostic reloads completed. Check visually for flicker; results are in Cue's data folder.");
  } catch (error) {
    iina.file.write("@data/cue-smoke-results.json", JSON.stringify({status:"failed",error:String(error),rows,
      mpv:iina.mpv.getString("mpv-version"),tracks:tracks(),sid:iina.mpv.getString("sid")},null,2));
    throw error;
  } finally {
    const own = ownedTrack(tracks(),path);
    const restore = current() && own && String(own.id) === iina.mpv.getString("sid");
    renderer.remove();
    if (restore) iina.mpv.set("sid",previous);
  }
}
