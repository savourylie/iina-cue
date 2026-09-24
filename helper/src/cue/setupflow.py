"""Consent-gated download of the pinned model files.

Nothing here opens a network connection until an allow-listed start or
resume action. URLs are built only from the manifest's repository and
revision. Partial files stay beside the destination until the hash matches.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from .core import CueError

ACTIONS = frozenset({"start", "resume", "cancel", "verify", "smoke"})
_ATTEMPTS = 4


def pause(seconds: float) -> None:
    time.sleep(seconds)


def disk_free(path: Path) -> int:
    target = path if path.exists() else path.parent
    return shutil.disk_usage(target).free


def source_url(repository: str, revision: str, relative: str) -> str:
    return f"https://huggingface.co/{repository}/resolve/{revision}/{relative}"


def _files(manifest: dict):
    for asset in manifest["assets"]:
        for item in asset["files"]:
            yield asset, item


def destination(models: Path, asset: dict, item: dict) -> Path:
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts or item["path"] != relative.as_posix():
        raise CueError("UNSAFE_PATH")
    path = models / asset["folder"] / relative
    if path.is_symlink():
        raise CueError("UNSAFE_PATH")
    return path


def partial_path(dest: Path) -> Path:
    path = dest.with_name(dest.name + ".partial")
    if path.is_symlink():
        raise CueError("UNSAFE_PATH")
    return path


_verified: dict[tuple[str, int, int], bool] = {}


def _digest_matches(path: Path, item: dict) -> bool:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != item["bytes"]:
        return False
    if item.get("sha256"):
        digest = hashlib.sha256()
    else:
        digest = hashlib.sha1()
        digest.update(f"blob {item['bytes']}\0".encode())
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    expected = item["sha256"] or item["git_blob"]
    return digest.hexdigest() == expected


def _installed(path: Path, item: dict) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    info = path.stat()
    if info.st_size != item["bytes"]:
        return False
    key = (str(path), info.st_mtime_ns, info.st_size)
    known = _verified.get(key)
    if known is None:
        known = _digest_matches(path, item)
        _verified[key] = known
    return known


def _have(models: Path, asset: dict, item: dict) -> tuple[str, int]:
    dest = destination(models, asset, item)
    if _installed(dest, item):
        return "installed", item["bytes"]
    partial = partial_path(dest)
    if partial.is_file() and not partial.is_symlink():
        size = partial.stat().st_size
        if 0 < size <= item["bytes"]:
            return "partial", size
    return "missing", 0


def bytes_needed(manifest: dict, models: Path) -> int:
    needed = 0
    for asset, item in _files(manifest):
        state, have = _have(models, asset, item)
        if state != "installed":
            needed += item["bytes"] - have
    return needed


def _read_progress(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def describe(manifest: dict, models: Path, saved: dict | None = None) -> dict:
    saved = saved or {}
    assets = []
    sources = []
    total = installed = 0
    for asset in manifest["assets"]:
        sources.append(f"https://huggingface.co/{asset['repository']}/tree/{asset['revision']}")
        files = []
        for item in asset["files"]:
            state, have = _have(models, asset, item)
            total += item["bytes"]
            if state == "installed":
                installed += item["bytes"]
            files.append({"path": item["path"], "bytes": item["bytes"], "state": state, "bytes_done": have})
        assets.append({"name": asset["name"], "repository": asset["repository"], "revision": asset["revision"],
                       "folder": asset["folder"], "files": files})
    smoke = saved.get("smoke") if isinstance(saved.get("smoke"), dict) else None
    files_ready = bytes_needed(manifest, models) == 0 and all(f["state"] == "installed" for a in assets for f in a["files"])
    return {
        "ready": bool(files_ready and smoke and smoke.get("passed") is True),
        "files_ready": files_ready,
        "assets": assets,
        "bytes_total": total,
        "bytes_installed": installed,
        "bytes_needed": bytes_needed(manifest, models),
        "free_disk_bytes": disk_free(models),
        "sources": sources,
        "progress": {
            "phase": saved.get("phase") or "idle",
            "bytes_done": installed + sum(f["bytes_done"] for a in assets for f in a["files"] if f["state"] == "partial"),
            "bytes_total": total,
            "file": saved.get("file"),
            "error": saved.get("error"),
        },
        "smoke": smoke,
    }


def _open(url: str, headers: dict):
    request = urllib.request.Request(url, headers=headers)
    try:
        return urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        return exc


def _fetch(url: str, dest: Path, total: int, item: dict, cancel: threading.Event) -> None:
    partial = partial_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset > total:
        partial.unlink()
        offset = 0
    attempt = 0
    while offset < total:
        if cancel.is_set():
            raise CueError("CANCELLED")
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            response = _open(url, headers)
            status = getattr(response, "status", None) or response.getcode()
            if status >= 500 or status == 429:
                raise urllib.error.URLError(f"transient {status}")
            if status == 200 and offset:
                offset = 0
                mode = "wb"
            elif status == 206 or (status == 200 and offset == 0):
                mode = "ab" if status == 206 else "wb"
            else:
                raise CueError("MODEL_DOWNLOAD_FAILED", f"unexpected status {status}")
            with partial.open(mode) as out:
                while offset < total:
                    if cancel.is_set():
                        raise CueError("CANCELLED")
                    block = response.read(min(1024 * 1024, total - offset))
                    if not block:
                        break
                    out.write(block)
                    offset += len(block)
        except CueError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            attempt += 1
            if attempt >= _ATTEMPTS:
                raise CueError("MODEL_DOWNLOAD_FAILED", "download failed after retries")
            pause(0.5 * (2 ** (attempt - 1)))
            offset = partial.stat().st_size if partial.is_file() else 0
            continue
        attempt = 0
        if offset < total:
            attempt = 1
            pause(0.5)
    if not _digest_matches(partial, item):
        partial.unlink(missing_ok=True)
        raise CueError("MODEL_DOWNLOAD_FAILED", "checksum mismatch")
    partial.replace(dest)


def write_tone(path: Path) -> None:
    import math
    import struct
    rate, count = 16000, 1600
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(count))
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(frames), b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16, b"data", len(frames))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + frames)


class Setup:
    def __init__(self, models: Path, manifest_path: Path):
        self.models = models
        self.manifest_path = manifest_path
        self.progress_path = models / ".setup-progress.json"
        self.cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.models.mkdir(parents=True, exist_ok=True)

    def manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text())

    def _save(self, **fields) -> None:
        current = _read_progress(self.progress_path)
        current.update(fields)
        temporary = self.progress_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(current))
        temporary.replace(self.progress_path)

    def status(self) -> dict:
        from .core import digest
        body = describe(self.manifest(), self.models, _read_progress(self.progress_path))
        body["model_manifest"] = digest(self.manifest())
        return body

    def _require_space(self) -> None:
        needed = bytes_needed(self.manifest(), self.models)
        free = disk_free(self.models)
        if needed and free < needed:
            raise CueError("DISK_FULL", str(needed))

    def _download(self) -> None:
        try:
            for asset, item in _files(self.manifest()):
                if self.cancel.is_set():
                    self._save(phase="cancelled", error=None)
                    return
                state, _have_bytes = _have(self.models, asset, item)
                if state == "installed":
                    continue
                relative = f"{asset['folder']}/{item['path']}"
                self._save(phase="downloading", file=relative, error=None)
                url = source_url(asset["repository"], asset["revision"], item["path"])
                _fetch(url, destination(self.models, asset, item), item["bytes"], item, self.cancel)
            self._save(phase="idle", file=None, error=None)
        except CueError as exc:
            phase = "cancelled" if exc.code == "CANCELLED" else "error"
            self._save(phase=phase, error={"code": exc.code, "detail": str(exc)})

    def action(self, body: dict) -> dict:
        action = body.get("action")
        if not isinstance(action, str) or action not in ACTIONS:
            raise CueError("INVALID_REQUEST")
        if action == "cancel":
            self.cancel.set()
            self._save(phase="cancelled", error=None)
            return self.status()
        if action == "verify":
            self._save(phase="verified" if bytes_needed(self.manifest(), self.models) == 0 else "incomplete", error=None)
            return self.status()
        if action == "smoke":
            return self._smoke()
        self._require_space()
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self.cancel = threading.Event()
            self._save(phase="downloading", error=None)
            self._thread = threading.Thread(target=self._download, name="cue-setup", daemon=True)
            self._thread.start()
        return self.status()

    def _smoke(self) -> dict:
        clip = self.models.parent / "smoke-clip.wav"
        write_tone(clip)
        gemma = self.models / "gemma" / "gemma-4-E2B-it.litertlm"
        aligner = self.models / "aligner" / "model.safetensors"
        if gemma.is_symlink() or aligner.is_symlink() or not gemma.is_file() or not aligner.is_file():
            result = {"passed": False, "reason": "models are not installed", "clip": clip.name}
        else:
            result = _run_smoke(self.models, clip)
        self._save(phase="smoke", smoke=result, error=None if result["passed"] else {"code": "SMOKE_FAILED", "detail": result["reason"]})
        body = self.status()
        body["smoke"] = result
        return body


def _run_smoke(models: Path, clip: Path) -> dict:
    """Transcribe and align the synthesized clip. Failure keeps a reason."""
    try:
        from .media import Media
        from .pipeline import Pipeline
        media = Media.open(str(clip))
        pipeline = Pipeline(models, models.parent / "audio-temp")
        prepared = pipeline.run(media, 0, min(media.duration_ms, 1000), 0, "smoke")
        text = " ".join(cue.text for cue in prepared.cues).strip()
        if not prepared.cues:
            return {"passed": False, "reason": "alignment produced no cues", "clip": clip.name}
        return {"passed": True, "reason": text or "alignment produced cues", "clip": clip.name}
    except CueError as exc:
        return {"passed": False, "reason": str(exc) or exc.code, "clip": clip.name}
    except Exception as exc:
        return {"passed": False, "reason": exc.__class__.__name__, "clip": clip.name}
