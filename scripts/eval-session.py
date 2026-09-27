"""Drive a real helper session from this checkout: supervisor, worker, models and cache.

The simulated viewer sits at the settled end of coverage and never runs ahead, like a
player that waits for captions. Prints a JSON summary, then the side-by-side dump.
Only the media file you name is read; nothing else is searched or uploaded.

  .venv/bin/python scripts/eval-session.py --media /abs/film.mp4 --from-ms 115000 --to-ms 1262000 --target zh-TW --source en
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
import time
from pathlib import Path
os.environ.setdefault("CUE_INSTALLED", "0")
from cue.bootstrap import models_root, runtime_root
from cue.core import continuous_end, ranges_merge
from cue.glossary import load_user_glossary
from cue.report import dump_report
from cue.service import Supervisor

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", required=True); ap.add_argument("--target", default="zh-TW"); ap.add_argument("--source", default="auto")
    ap.add_argument("--from-ms", type=int, default=0); ap.add_argument("--to-ms", type=int, required=True)
    ap.add_argument("--timeout-s", type=int, default=3600)
    ap.add_argument("--model", help="speech model id from models/manifest.json (e2b, e4b); default: the model chosen in Advanced, else e2b")
    args = ap.parse_args()
    sup = Supervisor(runtime_root(), models_root())
    if args.model:
        # Only this run uses the model; the choice saved by Advanced is untouched.
        sup.speech_model = args.model
    client = sup.request("POST", "/v1/clients", {}, None)["client_id"]
    snap = sup.request("POST", "/v1/sessions", {"request_id": "eval", "path": str(Path(args.media).resolve()), "position_ms": args.from_ms,
                                                  "settings": {"target": args.target, "source": args.source}}, client)
    sid = snap["session_id"]; s = sup.sessions[sid]
    base = f"/v1/sessions/{sid}"
    seq, position, deadline = 1, args.from_ms, time.monotonic() + args.timeout_s
    windows, last = [], None
    try:
        while time.monotonic() < deadline:
            sup.tick()
            if s.timings and s.timings is not last:
                windows.append(s.timings); last = s.timings
            # Acknowledge each prepared snapshot as installed, like the plugin does.
            if s.artifact and s.installed_revision != s.artifact["revision"]:
                sup.request("POST", base + "/render-ack", {"revision": s.artifact["revision"], "sha256": s.artifact["sha256"], "seek_epoch": s.epoch, "success": True}, client)
            if s.state == "error":
                print(json.dumps({"session_error": s.error}), flush=True); break
            settled = continuous_end(ranges_merge([*s.prepared, *s.skipped_language, *s.failed]), position)
            if settled >= args.to_ms:
                break
            if settled > position:
                position = min(settled, args.to_ms); seq += 1
                sup.request("PUT", base + "/playback", {"client_seq": seq, "seek_epoch": s.epoch, "position_ms": position, "rate": 1}, client)
            sup.request("GET", base + "/snapshot", {}, client)
            time.sleep(.2)
    finally:
        summary = {"prepared": s.prepared, "failed": s.failed, "skipped_language": s.skipped_language, "windows": len(windows),
                   "translate_s_mean": round(sum(w.get("translate_s", 0) for w in windows) / max(1, len(windows)), 2),
                   "held_back_ms_total": sum(w.get("held_back_ms", 0) for w in windows),
                   "translation_units": sum(w.get("translation_units", 0) for w in windows),
                   "names_learned": sum(w.get("names_learned", 0) for w in windows),
                   "rtf_mean": round(sum(w.get("rtf", 0) for w in windows) / max(1, len(windows)), 3),
                   "asr_s_mean": round(sum(w.get("asr_s", 0) for w in windows) / max(1, len(windows)), 2),
                   "align_s_mean": round(sum(w.get("align_s", 0) for w in windows) / max(1, len(windows)), 2),
                   "peak_rss_gb": round(max((w.get("process_peak_rss_bytes", 0) for w in windows), default=0) / 2**30, 2),
                   "speech_model": sup.speech_model,
                   "names_rejected_by_worker": dict(Counter(f"{k} → {v}" for w in windows for k, v in w.get("names_rejected", {}).items()))}
        signature, path = s.media.signature, s.media.path
        sup.request("DELETE", base, {}, client); sup.stop_worker()
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    print(dump_report(sup.cache, signature, args.target, load_user_glossary(path, runtime_root(), args.target), args.from_ms, args.to_ms))

if __name__ == "__main__":
    main()
