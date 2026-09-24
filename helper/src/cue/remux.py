"""Copy local media streams into a new container with a zero-based timeline."""
from __future__ import annotations
import errno
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable
from .core import CueError
from .media import binary, local_media, probe

OUTPUT_SUFFIXES = {".mkv", ".mov", ".mp4", ".m4v"}
RemuxProgress = Callable[[str, int | None], None]

def validate_destination(source: str, output: str) -> tuple[Path, Path]:
    src = local_media(source)
    dest = Path(output)
    if (not dest.is_absolute() or ".." in dest.parts or dest.suffix.lower() not in OUTPUT_SUFFIXES
            or not dest.parent.is_dir() or dest.parent.is_symlink() or dest.is_symlink()):
        raise CueError("UNSAFE_PATH", "choose a new absolute .mkv, .mov, or .mp4 path")
    if src == dest:
        raise CueError("UNSAFE_PATH", "the source file is never overwritten")
    if dest.exists(): raise CueError("OUTPUT_EXISTS")
    return src, dest

def _streams(streams: list[dict]) -> list[tuple[str | None, str | None]]:
    return [(s.get("codec_type"), s.get("codec_name")) for s in streams]

def _positive_seconds(value) -> float | None:
    try: seconds = float(value)
    except (TypeError, ValueError): return None
    return seconds if math.isfinite(seconds) and seconds > 0 else None

def _duration_seconds(info: dict) -> float | None:
    fmt = info.get("format", {})
    duration = _positive_seconds(fmt.get("duration"))
    if duration is not None:
        start = _positive_seconds(fmt.get("start_time"))
        return duration - start if start is not None and start < duration else duration
    streams = [_positive_seconds(s.get("duration")) for s in info.get("streams", [])]
    return max((value for value in streams if value is not None), default=None)

def _progress_percent(fields: dict[str, str], duration: float | None) -> int | None:
    if duration is None: return None
    try:
        micros = fields.get("out_time_us") or fields.get("out_time_ms")
        if micros is not None:
            seconds = int(micros) / 1_000_000
        else:
            hours, minutes, seconds_text = fields["out_time"].split(":")
            seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_text)
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(seconds): return None
    return max(0, min(99, int(seconds / duration * 100)))

def _check_cancel(cancel: threading.Event | None):
    if cancel is not None and cancel.is_set(): raise CueError("REMUX_CANCELLED")

def remux(source: str, output: str, progress: RemuxProgress | None = None, cancel: threading.Event | None = None) -> str:
    """Cancellation is honored until the output is committed; after that the copy completes."""
    src, dest = validate_destination(source, output)
    _check_cancel(cancel)
    before = src.stat()
    original = probe(src)
    copyable = [stream for stream in original["streams"] if stream.get("codec_type") != "data"]
    if not any(stream.get("codec_type") in {"video", "audio", "subtitle"} for stream in copyable):
        raise CueError("MEDIA_UNSUPPORTED", "no video, audio, or subtitle stream to remux")
    has_data_streams = len(copyable) != len(original["streams"])
    duration = _duration_seconds(original)
    def report(phase: str, percent: int | None):
        if progress:
            try: progress(phase, percent)
            except Exception: pass  # Progress reporting must not interrupt the copy.
    fd, temporary = tempfile.mkstemp(prefix=".cue-remux-", suffix=dest.suffix, dir=dest.parent)
    os.close(fd)
    temp = Path(temporary)
    try:
        # No shell or re-encoding. FFmpeg removes the input start offset when
        # copyts is absent. Leave muxer shifting disabled: make_zero can move
        # the first visible PTS forward by a B-frame decode delay.
        argv = [binary("ffmpeg"), "-nostdin", "-v", "error", "-stats_period", "0.5", "-progress", "pipe:1", "-fflags", "+genpts",
                "-i", str(src), "-map", "0"]
        if has_data_streams: argv += ["-map", "-0:d"]
        argv += ["-map_metadata", "0", "-map_chapters", "0", "-c", "copy",
                 "-avoid_negative_ts", "disabled", "-y", str(temp)]
        report("copying", 0 if duration is not None else None)
        with tempfile.TemporaryFile() as errors:
            with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=errors, text=True, bufsize=1) as run:
                def read_progress():
                    fields: dict[str, str] = {}
                    last_percent = -1
                    assert run.stdout is not None
                    for line in run.stdout:
                        key, separator, value = line.strip().partition("=")
                        if not separator: continue
                        fields[key] = value
                        if key == "progress":
                            percent = _progress_percent(fields, duration)
                            if percent is not None and percent > last_percent:
                                last_percent = percent
                                report("copying", percent)
                            fields = {}
                reader = threading.Thread(target=read_progress, name="cue-remux-progress", daemon=True)
                reader.start()
                deadline = time.monotonic() + 7200
                try:
                    while True:
                        try:
                            returncode = run.wait(timeout=.25)
                            break
                        except subprocess.TimeoutExpired:
                            if cancel is not None and cancel.is_set():
                                run.terminate()
                                try: run.wait(timeout=5)
                                except subprocess.TimeoutExpired: run.kill(); run.wait()
                                raise CueError("REMUX_CANCELLED")
                            if time.monotonic() > deadline:
                                run.kill(); run.wait()
                                raise CueError("REMUX_FAILED", "FFmpeg timed out")
                finally: reader.join(timeout=5)
            if returncode:
                raise CueError("REMUX_FAILED", "FFmpeg could not copy every stream into the selected container")
        _check_cancel(cancel)
        report("verifying", 99)
        after = src.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise CueError("SOURCE_CHANGED")
        result = probe(temp)
        if _streams(copyable) != _streams(result["streams"]):
            raise CueError("REMUX_VERIFY_FAILED", "output stream types or codecs differ")
        for source_stream, output_stream in zip(copyable, result["streams"]):
            source_duration, output_duration = source_stream.get("duration"), output_stream.get("duration")
            if source_duration not in (None, "N/A") and output_duration not in (None, "N/A"):
                expected = float(source_duration)
                if abs(float(output_duration)-expected) > max(.25, expected*.01):
                    raise CueError("REMUX_VERIFY_FAILED", "output stream duration differs")
        starts = [float(s["start_time"]) for s in result["streams"] if s.get("start_time") not in (None, "N/A")]
        if not starts or not -.1 <= min(starts) <= .1:
            raise CueError("REMUX_VERIFY_FAILED", "output did not start near zero")
        if temp.stat().st_size == 0:
            raise CueError("REMUX_VERIFY_FAILED", "empty output")
        _check_cancel(cancel)
        report("saving", 99)
        try:
            # Hard-linking is an exclusive final commit: it cannot replace a
            # file created while FFmpeg was running and needs no cross-volume move.
            os.link(temp, dest)
        except FileExistsError as exc:
            raise CueError("OUTPUT_EXISTS") from exc
        except OSError as exc:
            if exc.errno not in {errno.EPERM, errno.ENOTSUP, errno.ENOSYS}:
                raise
            # exFAT and some external disks lack hard links. Exclusive create
            # still protects an existing file; remove an incomplete copy if
            # this process sees a write failure.
            created = False
            try:
                with temp.open("rb") as source_file, dest.open("xb") as output_file:
                    created = True
                    shutil.copyfileobj(source_file, output_file, length=1024 * 1024)
                    output_file.flush(); os.fsync(output_file.fileno())
            except FileExistsError as exists:
                raise CueError("OUTPUT_EXISTS") from exists
            except Exception:
                if created: dest.unlink(missing_ok=True)
                raise
        return str(dest)
    finally:
        temp.unlink(missing_ok=True)
