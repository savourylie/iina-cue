from __future__ import annotations
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from .core import Cue, CueError, ranges_merge, srt

def private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise CueError("UNSAFE_PATH")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise CueError("UNSAFE_PATH")
    path.chmod(0o700)
    return path

def atomic_write(path: Path, text: str) -> None:
    private_dir(path.parent)
    if path.is_symlink():
        raise CueError("UNSAFE_PATH")
    fd, tmp = tempfile.mkstemp(prefix=".cue-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class Cache:
    def __init__(self, root: Path):
        self.root = private_dir(root)
        path = root / "cache.sqlite3"
        if path.is_symlink(): raise CueError("UNSAFE_PATH")
        self.db = sqlite3.connect(path, check_same_thread=False)
        path.chmod(0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS chunks (
            profile TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
            payload TEXT NOT NULL, updated REAL NOT NULL DEFAULT (unixepoch()),
            PRIMARY KEY(profile, start, end));
          CREATE TABLE IF NOT EXISTS profiles (
            profile TEXT PRIMARY KEY, media TEXT NOT NULL, target TEXT NOT NULL);
          PRAGMA user_version=1;
        """)

    def register(self, profile: str, media: str, target: str):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO profiles VALUES (?,?,?)", (profile, media, target))

    def put(self, profile: str, start: int, end: int, cues: list[Cue], language: dict):
        srt(cues)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO chunks (profile,start,end,payload) VALUES (?,?,?,?)",
                            (profile, start, end, json.dumps({"cues": [asdict(c) for c in cues], "language": language}, ensure_ascii=False)))

    def read(self, profile: str) -> tuple[list[list[int]], list[Cue], dict]:
        ranges, cues, language = [], {}, {"code": "und", "status": "unknown"}
        for start, end, payload in self.db.execute("SELECT start,end,payload FROM chunks WHERE profile=? ORDER BY start", (profile,)):
            data = json.loads(payload); ranges.append([start, end]); language = data["language"]
            for row in data["cues"]: cues[row["id"]] = Cue(**row)
        ordered = sorted(cues.values(), key=lambda c: (c.start_ms, c.end_ms))
        # Time+text overlap dedupe only; conflicting boundaries remain an error.
        deduped = []
        for c in ordered:
            if deduped and c.start_ms < deduped[-1].end_ms:
                prev = deduped[-1]
                if c.text == prev.text and abs(c.start_ms-prev.start_ms) < 300:
                    continue
                raise CueError("ALIGNMENT_FAILED", "conflicting chunk boundary; retry with more context")
            deduped.append(c)
        return ranges_merge(ranges), deduped, language

    def clear_media(self, media: str):
        with self.db:
            self.db.execute("DELETE FROM chunks WHERE profile IN (SELECT profile FROM profiles WHERE media=?)", (media,))
            self.db.execute("DELETE FROM profiles WHERE media=?", (media,))

    def status(self):
        return {"profiles": self.db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0],
                "chunks": self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "bytes": sum(p.stat().st_size for p in self.root.glob("cache.sqlite3*"))}

    def export(self, profile: str, duration: int, destination: Path, metadata: dict) -> Path:
        ranges, cues, _ = self.read(profile)
        complete = ranges == [[0, duration]]
        if destination.suffix.lower() != ".srt": raise CueError("UNSAFE_PATH", "export path must end in .srt")
        name = destination.name
        if not complete and not name.endswith(".partial.srt"):
            name = destination.stem + ".partial.srt"
        dest = destination.with_name(name)
        sidecar = dest.with_suffix(".json")
        if not dest.parent.is_dir() or dest.is_symlink() or sidecar.is_symlink(): raise CueError("UNSAFE_PATH")
        # Exclusive creation never overwrites another subtitle or media file.
        created_srt = created_sidecar = False
        try:
            content = srt(cues)
            with dest.open("x", encoding="utf-8") as f:
                created_srt = True
                f.write(content)
            with sidecar.open("x", encoding="utf-8") as f:
                created_sidecar = True
                json.dump({**metadata, "complete_movie": complete, "coverage": ranges}, f, ensure_ascii=False, indent=2)
        except FileExistsError as exc:
            if created_srt: dest.unlink(missing_ok=True)
            if created_sidecar: sidecar.unlink(missing_ok=True)
            raise CueError("OUTPUT_EXISTS") from exc
        except Exception:
            if created_srt: dest.unlink(missing_ok=True)
            if created_sidecar: sidecar.unlink(missing_ok=True)
            raise
        return dest
