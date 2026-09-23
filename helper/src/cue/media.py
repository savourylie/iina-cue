"""Verified stream selection and bounded PCM extraction with explicit PTS origin."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from .core import CueError, digest

def binary(name: str) -> str:
    for path in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}", shutil.which(name)):
        if path and Path(path).is_file():
            return path
    raise CueError("SETUP_REQUIRED", f"{name} unavailable")

def local_media(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts or p.is_symlink() or not p.is_file() or p.suffix.lower() not in {".mp4", ".mkv", ".mov", ".m4v", ".webm", ".wav", ".m4a"}:
        raise CueError("MEDIA_UNSUPPORTED")
    return p.resolve(strict=True)

def fingerprint(path: Path) -> str:
    stat = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for offset in sorted({0, max(0, stat.st_size // 2 - 32768), max(0, stat.st_size - 65536)}):
            f.seek(offset); h.update(f.read(65536))
    return digest(["sample-v1", stat.st_size, stat.st_mtime_ns, h.hexdigest()])

def probe(path: Path) -> dict:
    run = subprocess.run([binary("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, timeout=15)
    if run.returncode:
        raise CueError("MEDIA_UNSUPPORTED")
    return json.loads(run.stdout)

def select_stream(info: dict, hint: dict) -> dict:
    streams = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not streams:
        raise CueError("NO_AUDIO_TRACK")
    if hint.get("external"):
        raise CueError("MEDIA_UNSUPPORTED", "external audio")
    ff = hint.get("ff_index")
    candidates = streams
    if ff is not None:
        candidates = [s for s in streams if s["index"] == ff]
    for field, key in (("codec", "codec_name"), ("channels", "channels")):
        if hint.get(field):
            candidates = [s for s in candidates if s.get(key) == hint[field]]
    for field in ("language", "title"):
        if hint.get(field):
            matches = [s for s in candidates if s.get("tags", {}).get(field) == hint[field]]
            if matches:
                candidates = matches
            elif any(s.get("tags", {}).get(field) for s in candidates):
                candidates = []
    if len(candidates) != 1:
        raise CueError("AUDIO_TRACK_MAPPING_AMBIGUOUS")
    # Never compare mpv's ID to a stream index.
    return candidates[0]

@dataclass(frozen=True)
class Media:
    path: str
    signature: str
    stream_index: int
    stream_key: str
    duration_ms: int
    origin_seconds: float
    size: int
    mtime_ns: int

    @classmethod
    def open(cls, path: str, hint: dict) -> "Media":
        p = local_media(path)
        info = probe(p)
        stream = select_stream(info, hint)
        fmt = info["format"]
        duration = round(float(fmt["duration"]) * 1000)
        if duration <= 0:
            raise CueError("MEDIA_UNSUPPORTED")
        sig = fingerprint(p)
        stat = p.stat()
        return cls(str(p), sig, stream["index"], digest([sig, stream, "pts-pad-v1"]), duration, float(fmt.get("start_time", 0)), stat.st_size, stat.st_mtime_ns)

    def unchanged(self) -> bool:
        try:
            stat = os.stat(self.path)
            return stat.st_size == self.size and stat.st_mtime_ns == self.mtime_ns
        except OSError:
            return False

def extract(media: Media, start_ms: int, end_ms: int, dest: Path) -> dict:
    if not media.unchanged():
        raise CueError("SOURCE_CHANGED")
    if not 0 <= start_ms < end_ms <= media.duration_ms or end_ms - start_ms > 30000:
        raise CueError("MEDIA_UNSUPPORTED", "invalid audio window")
    # copyts keeps source timestamps after fast input seek. Reset relative to the
    # container origin, resample with first_pts=0 to pad late-starting audio,
    # trim by sample count. Sample zero is thus explicitly the requested point.
    absolute = media.origin_seconds + start_ms / 1000
    duration = (end_ms - start_ms) / 1000
    af = f"asetpts=PTS-({absolute})/TB,aresample=16000:async=1:first_pts=0,apad,atrim=end_sample={round(duration*16000)}"
    argv = [binary("ffmpeg"), "-nostdin", "-v", "error", "-threads", "2", "-copyts", "-ss", str(start_ms / 1000), "-i", media.path,
            "-map", f"0:{media.stream_index}", "-vn", "-af", af, "-ac", "1", "-ar", "16000", "-t", str(duration), "-c:a", "pcm_f32le", "-y", str(dest)]
    run = subprocess.run(argv, capture_output=True, timeout=45)
    if run.returncode:
        raise CueError("MEDIA_UNSUPPORTED", "audio extraction failed")
    return {"sample_zero_media_ms": start_ms, "sample_rate_hz": 16000, "sample_count": round(duration*16000), "time_mapping_version": "pts-pad-v1"}
