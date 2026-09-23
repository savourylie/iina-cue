from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from .bootstrap import PROJECT, call, connection, ensure, models_root, runtime_root
from .core import Cue, CueError, Settings, digest, srt
from .doctor import doctor
from .media import Media, fingerprint, local_media
from .storage import Cache, atomic_write

def benchmark(args):
    from .pipeline import Pipeline
    if not args.media:
        raise CueError("MEDIA_REQUIRED", "Provide --media /absolute/path.mp4 --duration-ms 180000; no private folders are searched")
    media = Media.open(str(Path(args.media).resolve()), {"ff_index": args.stream} if args.stream is not None else {})
    settings = Settings(target=args.mode, source=args.source)
    start, limit = args.from_ms, min(media.duration_ms, args.from_ms+args.duration_ms)
    if not 0 <= start < limit: raise CueError("INVALID_REQUEST")
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(models_root(), runtime_root()/"audio-temp")
    runs = []
    try:
        for run in range(args.runs):
            batches, cues, source_cues = [], [], []
            t = time.monotonic(); pos = start
            while pos < limit:
                end = min(limit, pos + (settings.first_ms if pos == start else settings.window_ms))
                result = pipeline.run({"media": asdict(media), "settings": asdict(settings), "range": [pos,end], "source_profile": digest([media.stream_key,settings.source]), "previous_source": source_cues[-1:]})
                # Explicit benchmark output includes transcripts for boundary review.
                atomic_write(out/f"run-{run+1}-batch-{len(batches)+1}.json", json.dumps(result, ensure_ascii=False, indent=2))
                cues.extend(Cue(**c) for c in result["rendered"])
                source_cues.extend(result["source"])
                batches.append({"range": result["committed_range"], "timings": result["timings"], "language": result["language"], "mapping": result["mapping"]})
                # Rendering/persistence is inside the measured wall time.
                atomic_write(out/f"run-{run+1}.partial.srt", srt(cues))
                pos = result["committed_range"][1]
            elapsed = time.monotonic()-t
            runs.append({"model_state": "cold" if run == 0 else "warm", "elapsed_s": elapsed, "unique_media_seconds": (limit-start)/1000,
                         "pipeline_rtf": elapsed/((limit-start)/1000), "batches": batches, "iina_install_ack": "not_run"})
            atomic_write(out/"benchmark.json", json.dumps({"environment": doctor(models_root()), "runs": runs}, indent=2))
    finally: pipeline.backend.close()
    return {"output": str(out), "runs": [{k:v for k,v in x.items() if k != "batches"} for x in runs]}

def main():
    parser = argparse.ArgumentParser(prog="cue-helper")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "ensure", "serve", "shutdown"): commands.add_parser(name)
    b = commands.add_parser("benchmark")
    b.add_argument("--media"); b.add_argument("--from-ms", type=int, default=0); b.add_argument("--duration-ms", type=int, default=180000)
    b.add_argument("--mode", choices=["original","zh-TW","zh-CN","en","ja","ko"], default="zh-TW")
    b.add_argument("--source", choices=["auto","en","zh","ja","ko"], default="auto")
    b.add_argument("--stream", type=int); b.add_argument("--runs", type=int, default=2); b.add_argument("--output", default="benchmarks/results/local-benchmark")
    c = commands.add_parser("cache"); c.add_argument("action", choices=["status","clear"]); c.add_argument("--media")
    e = commands.add_parser("export"); e.add_argument("--media", required=True); e.add_argument("--target", choices=["original","zh-TW","zh-CN","en","ja","ko"], default="zh-TW"); e.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor": result = doctor(models_root())
        elif args.command == "ensure": result = ensure(runtime_root())
        elif args.command == "serve":
            from .service import serve
            serve(runtime_root(), models_root()); return
        elif args.command == "shutdown": result = call(connection(runtime_root()), "/shutdown", {})
        elif args.command == "benchmark": result = benchmark(args)
        else:
            cache = Cache(runtime_root()/"cache")
            if args.command == "cache":
                if args.action == "clear":
                    if not args.media: raise CueError("MEDIA_REQUIRED")
                    cache.clear_media(fingerprint(local_media(str(Path(args.media).resolve()))))
                result = cache.status()
            else:
                media = Media.open(str(Path(args.media).resolve()), {})
                rows = cache.db.execute("SELECT profile FROM profiles WHERE media=? AND target=?", (media.signature,args.target)).fetchall()
                if len(rows) != 1: raise CueError("CACHE_PROFILE_AMBIGUOUS", "Export from the active IINA session to select an exact audio/profile")
                result = {"path": str(cache.export(rows[0][0], media.duration_ms, Path(args.output).resolve(), {"target":args.target}))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": {"code": exc.code if isinstance(exc,CueError) else type(exc).__name__, "detail": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

if __name__ == "__main__": main()
