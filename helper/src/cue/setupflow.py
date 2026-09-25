"""Consent-gated download of the pinned model files.

Nothing here opens a network connection until an allow-listed start or
resume action. URLs are built only from the manifest's repository and
revision. Partial files stay beside the destination until the hash matches.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from .core import CueError

MODEL_ACTIONS = frozenset({"model_download", "model_cancel", "model_use", "model_remove"})
ACTIONS = frozenset({"start", "resume", "cancel", "verify", "smoke"}) | MODEL_ACTIONS
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
_MARKERS = ".verified.json"
# The download thread and status requests on the helper's HTTP threads update the
# same small JSON files; each update is a read-modify-write that must not interleave.
_file_lock = threading.Lock()


def _replace_json(path: Path, data: dict) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(data))
    temporary.replace(path)


def _load_markers(models: Path) -> dict:
    path = models / _MARKERS
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_markers(models: Path, update: dict) -> None:
    """Remember files whose full hash matched, by size and modification time.
    A later status call trusts an unchanged file instead of hashing gigabytes again."""
    with _file_lock:
        data = _load_markers(models)
        data.update(update)
        _replace_json(models / _MARKERS, {k: v for k, v in data.items() if v is not None})


def _expected(item: dict) -> str:
    return item.get("sha256") or item.get("git_blob")


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


def _installed(path: Path, item: dict, models: Path | None = None, relative: str | None = None) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    info = path.stat()
    if info.st_size != item["bytes"]:
        return False
    key = (str(path), info.st_mtime_ns, info.st_size)
    known = _verified.get(key)
    stamp = [info.st_size, info.st_mtime_ns, _expected(item)]
    if known is None and models is not None and _load_markers(models).get(relative) == stamp:
        known = True
    if known is None:
        known = _digest_matches(path, item)
        if known and models is not None:
            _save_markers(models, {relative: stamp})
    _verified[key] = known
    return known


def _remember(models: Path, asset: dict, item: dict) -> None:
    """Record a file that _fetch has just verified before moving it into place."""
    dest = destination(models, asset, item)
    info = dest.stat()
    _save_markers(models, {f"{asset['folder']}/{item['path']}": [info.st_size, info.st_mtime_ns, _expected(item)]})
    _verified[(str(dest), info.st_mtime_ns, info.st_size)] = True


def _have(models: Path, asset: dict, item: dict) -> tuple[str, int]:
    dest = destination(models, asset, item)
    if _installed(dest, item, models, f"{asset['folder']}/{item['path']}"):
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


SMOKE_TEXT = "Cue is checking that speech recognition works on this Mac."


def write_speech(path: Path) -> None:
    """Speak a known English sentence with the system voice. No media is read from the user."""
    import subprocess
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    run = subprocess.run(["/usr/bin/say", "-o", str(path), "--file-format=WAVE", "--data-format=LEI16@16000", SMOKE_TEXT],
                         capture_output=True, timeout=60)
    if run.returncode != 0 or not path.is_file():
        raise CueError("SMOKE_FAILED", "the system voice could not write the test clip")


def speech_models(manifest: dict) -> list[dict]:
    """The speech models Cue can use. E2B is always first-run setup's model."""
    return manifest.get("speech_models") or [{"id": "e2b", "asset": "gemma", "file": "gemma-4-E2B-it.litertlm",
                                               "min_ram_bytes": 16 * 2 ** 30}]


def default_speech_model(manifest: dict) -> str:
    return manifest.get("default_speech_model", "e2b")


def speech_model(manifest: dict, model_id: object) -> dict:
    for choice in speech_models(manifest):
        if choice["id"] == model_id:
            return choice
    raise CueError("INVALID_REQUEST")


def find_asset(manifest: dict, name: str) -> tuple[dict, bool]:
    """An asset by name, and whether it is optional (downloaded only on request)."""
    for asset in manifest["assets"]:
        if asset["name"] == name:
            return asset, False
    for asset in manifest.get("optional_assets", []):
        if asset["name"] == name:
            return asset, True
    raise CueError("INVALID_REQUEST")


def speech_model_path(models: Path, manifest: dict, model_id: str) -> Path:
    choice = speech_model(manifest, model_id)
    asset, _ = find_asset(manifest, choice["asset"])
    item = next((item for item in asset["files"] if item["path"] == choice["file"]), {"path": choice["file"]})
    return destination(models, asset, item)


def speech_model_complete(models: Path, manifest: dict, model_id: str) -> bool:
    """The model's files are in place at their pinned sizes. Their hashes were checked
    before the model could be chosen; this cheap check runs at every helper start."""
    choice = speech_model(manifest, model_id)
    asset, _ = find_asset(manifest, choice["asset"])
    paths = [(destination(models, asset, item), item["bytes"]) for item in asset["files"]]
    return all(path.is_file() and not path.is_symlink() and path.stat().st_size == size for path, size in paths)


def machine_memory() -> int:
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def compile_caches(models: Path, filename: str) -> list[Path]:
    """LiteRT-LM's caches for one model file, named "<file>_<mtime>_<size>...", in models/compiled."""
    compiled = models / "compiled"
    if not compiled.is_dir():
        return []
    return [path for path in compiled.iterdir() if path.name.startswith(f"{filename}_")]


class Setup:
    def __init__(self, models: Path, manifest_path: Path, run_job=None, try_model=None, current_model=None):
        self.models = models
        # Sends one job to the supervisor's persistent worker and returns its reply.
        self.run_job = run_job
        # try_model(model_id, clip) restarts the worker with that model, runs the smoke
        # job, and keeps the model only if it passes. current_model() is the one in use.
        self.try_model = try_model
        self.current_model = current_model
        self.manifest_path = manifest_path
        self.progress_path = models / ".setup-progress.json"
        self.cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.models.mkdir(parents=True, exist_ok=True)

    def manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text())

    def _save(self, **fields) -> None:
        with _file_lock:
            current = _read_progress(self.progress_path)
            current.update(fields)
            _replace_json(self.progress_path, current)

    def status(self) -> dict:
        from .core import digest
        # Check the thread before reading the file: a thread that ends in between
        # has already saved its final phase.
        alive = bool(self._thread and self._thread.is_alive())
        body = describe(self.manifest(), self.models, _read_progress(self.progress_path))
        # A saved "downloading" outlives a stopped helper. No thread here means
        # nothing is downloading; a resume continues from the partial files.
        if body["progress"]["phase"] in {"downloading", "smoking"} and not alive:
            body["progress"]["phase"] = "interrupted"
        body["model_manifest"] = digest(self.manifest())
        body["speech_models"] = self._models_status(_read_progress(self.progress_path), alive)
        return body

    def _selected(self, manifest: dict) -> str:
        return self.current_model() if self.current_model else default_speech_model(manifest)

    def _models_status(self, saved: dict, alive: bool) -> dict:
        manifest = self.manifest()
        memory = machine_memory()
        selected = self._selected(manifest)
        models = []
        for choice in speech_models(manifest):
            asset, optional = find_asset(manifest, choice["asset"])
            have = [_have(self.models, asset, item) for item in asset["files"]]
            state = ("installed" if all(s == "installed" for s, _ in have)
                     else "partial" if any(s != "missing" for s, _ in have) else "missing")
            download = sum(item["bytes"] for item in asset["files"])
            # Disk needed: the download plus the compile cache LiteRT-LM writes on first use.
            models.append({"id": choice["id"], "bytes": download, "disk_bytes": download + choice.get("cache_bytes", 0),
                           "bytes_done": sum(b for _, b in have), "state": state, "optional": optional,
                           "min_ram_bytes": choice["min_ram_bytes"], "fits_memory": memory >= choice["min_ram_bytes"],
                           "selected": choice["id"] == selected})
        download = saved.get("model_download") if isinstance(saved.get("model_download"), dict) else None
        trial = saved.get("model_trial") if isinstance(saved.get("model_trial"), dict) else None
        # A saved in-flight phase with no live thread means the helper stopped mid-way.
        if download and download.get("phase") == "downloading" and not alive:
            download = {**download, "phase": "interrupted"}
        if trial and trial.get("phase") == "smoking" and not alive:
            trial = {**trial, "phase": "interrupted"}
        return {"selected": selected, "ram_bytes": memory, "models": models, "download": download, "trial": trial}

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
            return self._start_smoke()
        if action in MODEL_ACTIONS:
            return self._model_action(action, body.get("model"))
        self._require_space()
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self.cancel = threading.Event()
            self._save(phase="downloading", error=None)
            self._thread = threading.Thread(target=self._download, name="cue-setup", daemon=True)
            self._thread.start()
        return self.status()

    def _model_action(self, action: str, model_id: object) -> dict:
        manifest = self.manifest()
        choice = speech_model(manifest, model_id)
        asset, optional = find_asset(manifest, choice["asset"])
        if action == "model_cancel":
            self.cancel.set()
            return self.status()
        if action == "model_remove":
            # E2B belongs to first-run setup and is never removed here.
            if not optional:
                raise CueError("INVALID_REQUEST")
            if self._selected(manifest) == choice["id"]:
                raise CueError("MODEL_IN_USE")
            with self._lock:
                if self._thread and self._thread.is_alive():
                    raise CueError("SETUP_BUSY")
                for item in asset["files"]:
                    dest = destination(self.models, asset, item)
                    dest.unlink(missing_ok=True)
                    partial_path(dest).unlink(missing_ok=True)
                    # The compile cache can be as large as the model; removing frees both.
                    for cache in compile_caches(self.models, item["path"]):
                        cache.unlink(missing_ok=True)
                _save_markers(self.models, {f"{asset['folder']}/{item['path']}": None for item in asset["files"]})
            return self.status()
        if machine_memory() < choice["min_ram_bytes"]:
            raise CueError("LOW_MEMORY", str(choice["min_ram_bytes"]))
        if action == "model_download":
            if not optional:
                raise CueError("INVALID_REQUEST")
            needed = sum(item["bytes"] - have for item in asset["files"]
                         for state, have in [_have(self.models, asset, item)] if state != "installed")
            if needed and not compile_caches(self.models, choice["file"]):
                needed += choice.get("cache_bytes", 0)
            if needed and disk_free(self.models) < needed:
                raise CueError("DISK_FULL", str(needed))
            with self._lock:
                if self._thread and self._thread.is_alive():
                    return self.status()
                self.cancel = threading.Event()
                self._save(model_download={"model": choice["id"], "phase": "downloading", "error": None})
                self._thread = threading.Thread(target=self._download_model, args=(choice["id"], asset), name="cue-model", daemon=True)
                self._thread.start()
            return self.status()
        # model_use: the model must be complete and verified before a trial.
        if not all(_have(self.models, asset, item)[0] == "installed" for item in asset["files"]):
            raise CueError("MODEL_NOT_INSTALLED")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise CueError("SETUP_BUSY")
            self._save(model_trial={"model": choice["id"], "phase": "smoking", "reason": None})
            self._thread = threading.Thread(target=self._trial, args=(choice["id"],), name="cue-model-trial", daemon=True)
            self._thread.start()
        return self.status()

    def _download_model(self, model_id: str, asset: dict) -> None:
        try:
            for item in asset["files"]:
                if self.cancel.is_set():
                    raise CueError("CANCELLED")
                if _have(self.models, asset, item)[0] == "installed":
                    continue
                self._save(model_download={"model": model_id, "phase": "downloading", "file": item["path"], "error": None})
                url = source_url(asset["repository"], asset["revision"], item["path"])
                _fetch(url, destination(self.models, asset, item), item["bytes"], item, self.cancel)
                _remember(self.models, asset, item)
            self._save(model_download={"model": model_id, "phase": "idle", "error": None})
        except CueError as exc:
            phase = "cancelled" if exc.code == "CANCELLED" else "error"
            self._save(model_download={"model": model_id, "phase": phase, "error": None if phase == "cancelled" else {"code": exc.code, "detail": str(exc)}})

    def _trial(self, model_id: str) -> None:
        try:
            clip = self.models.parent / "smoke-clip.wav"
            write_speech(clip)
            result = self.try_model(model_id, clip) if self.try_model else {"passed": False, "reason": "no inference worker"}
        except CueError as exc:
            result = {"passed": False, "reason": str(exc) or exc.code}
        except Exception as exc:
            result = {"passed": False, "reason": exc.__class__.__name__}
        self._save(model_trial={"model": model_id, "phase": "passed" if result["passed"] else "failed",
                                "reason": result.get("reason"), "seconds": result.get("seconds")})

    def _start_smoke(self) -> dict:
        manifest = self.manifest()
        gemma = speech_model_path(self.models, manifest, self._selected(manifest))
        aligner = self.models / "aligner" / "model.safetensors"
        if gemma.is_symlink() or aligner.is_symlink() or not gemma.is_file() or not aligner.is_file():
            result = {"passed": False, "reason": "models are not installed"}
            self._save(phase="smoke", smoke=result, error={"code": "SMOKE_FAILED", "detail": result["reason"]})
            return self.status()
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self._save(phase="smoking", smoke=None, error=None)
            self._thread = threading.Thread(target=self._smoke, name="cue-smoke", daemon=True)
            self._thread.start()
        return self.status()

    def _smoke(self) -> None:
        try:
            clip = self.models.parent / "smoke-clip.wav"
            write_speech(clip)
            result = _run_smoke(clip, self.run_job)
        except CueError as exc:
            result = {"passed": False, "reason": str(exc) or exc.code}
        except Exception as exc:
            result = {"passed": False, "reason": exc.__class__.__name__}
        self._save(phase="smoke", smoke=result, error=None if result["passed"] else {"code": "SMOKE_FAILED", "detail": result["reason"]})


def _run_smoke(clip: Path, run_job) -> dict:
    """Transcribe, align and translate the spoken clip in the persistent worker."""
    from dataclasses import asdict
    from .core import Settings, digest
    from .media import Media
    if run_job is None:
        return {"passed": False, "reason": "no inference worker"}
    media = Media.open(str(clip), {})
    settings = Settings(target="zh-TW", source="en")
    job = {"job_id": "setup-smoke", "media": asdict(media), "settings": asdict(settings), "range": [0, media.duration_ms],
           "source_profile": digest([media.stream_key, settings.source, "setup-smoke"]), "previous_source": []}
    reply = run_job(job)
    if "error" in reply:
        error = reply["error"]
        return {"passed": False, "reason": f"{error.get('code')}: {error.get('detail', '')}".rstrip(": ")}
    result = reply["result"]
    source = " ".join(cue["text"] for cue in result["source"]).strip()
    rendered = " ".join(cue["text"] for cue in result["rendered"]).strip()
    if not source or not rendered:
        return {"passed": False, "reason": "the test clip produced no subtitles"}
    timings = result.get("timings", {})
    return {"passed": True, "reason": source, "translation": rendered,
            "language": result["language"].get("code"), "seconds": round(timings.get("pipeline_s", 0), 1)}
