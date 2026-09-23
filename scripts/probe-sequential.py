#!/usr/bin/env python3
"""Drive one explicit local media session through its full remaining timeline.

Render acknowledgements are simulated; this checks the real helper/model/cache,
not uninterrupted native IINA playback. The media path is never written to the
result file or printed by this script.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "helper/src"))
from cue.bootstrap import call, connection  # noqa: E402
from cue.core import continuous_end  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--start-ms", type=int, default=20000)
    parser.add_argument("--target", choices=("original", "zh-TW", "en"), default="original")
    parser.add_argument("--timeout-s", type=int, default=600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    conn = connection(ROOT / ".runtime")
    client = call(conn, "/clients", {})["client_id"]
    session_id = None
    started = time.monotonic()
    result = {"status": "failed", "start_ms": args.start_ms, "target": args.target,
              "ack": "simulated; not native IINA playback", "error": None}
    try:
        created = call(conn, "/sessions", {"request_id": "sequential-" + uuid4().hex,
                       "path": str(args.media), "position_ms": args.start_ms,
                       "settings": {"source": "auto", "target": args.target}}, client)
        session_id = created["session_id"]
        base = "/sessions/" + session_id
        duration = created["duration_ms"]
        if not 0 <= args.start_ms < duration:
            raise ValueError("start outside media duration")
        result["duration_ms"] = duration
        frontier = args.start_ms
        sent_position = args.start_ms
        seq = 0
        acked_revision = 0
        last_printed = args.start_ms
        deadline = started + args.timeout_s
        while time.monotonic() < deadline:
            snapshot = call(conn, base + "/snapshot", client=client)
            if snapshot["error"]:
                result["error"] = snapshot["error"]
                break
            artifact = snapshot["artifact"]
            if artifact and artifact["revision"] > acked_revision:
                call(conn, base + "/render-ack", {"revision": artifact["revision"],
                     "sha256": artifact["sha256"], "seek_epoch": 0, "success": True}, client)
                acked_revision = artifact["revision"]
            end = continuous_end(snapshot["prepared_ranges"], args.start_ms)
            if end > frontier:
                frontier = end
                if frontier - last_printed >= 60000 or frontier == duration:
                    print(json.dumps({"covered_until_ms": frontier, "duration_ms": duration}), flush=True)
                    last_printed = frontier
            if frontier == duration:
                result["status"] = "pass"
                break
            next_position = max(args.start_ms, frontier - 1)
            if next_position != sent_position:
                seq += 1
                call(conn, base + "/playback", {"client_seq": seq, "seek_epoch": 0,
                     "position_ms": next_position, "rate": 1}, client, "PUT")
                sent_position = next_position
            time.sleep(.15)
        else:
            result["error"] = {"code": "TIMEOUT"}
        result["covered_until_ms"] = frontier
        result["elapsed_s"] = round(time.monotonic() - started, 3)
        result["acknowledged_revisions"] = acked_revision
    except Exception as exc:
        result["error"] = {"code": type(exc).__name__, "detail": str(exc)}
    finally:
        if session_id:
            try: call(conn, "/sessions/" + session_id, client=client, method="DELETE")
            except Exception: pass
        try: call(conn, "/client", client=client, method="DELETE")
        except Exception: pass
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
