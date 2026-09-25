from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from .core import CueError
from .storage import private_dir

PROJECT = Path(__file__).resolve().parents[3]
HELPER_VERSION = "0.1.7"
_INSTALLED_ON = {"1", "true", "yes"}
_INSTALLED_OFF = {"0", "false", "no"}

# IINA's utils.exec keeps only LC_ALL, so HOME is unset before later imports run.
if not os.environ.get("HOME"):
    os.environ["HOME"] = str(Path.home())

def support_dir() -> Path:
    override = os.environ.get("CUE_SUPPORT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Library" / "Application Support" / "Cue").resolve()

def installed_mode() -> bool:
    # The runtime launcher exports CUE_INSTALLED=1. scripts/cue-helper exports
    # 0 so this checkout keeps using .runtime after an install marker exists.
    # With the variable unset, a regular file at <support>/installed selects
    # installed mode. The installer (#008) writes that file.
    flag = os.environ.get("CUE_INSTALLED", "").strip().lower()
    if flag in _INSTALLED_OFF:
        return False
    if flag in _INSTALLED_ON:
        enabled = True
    else:
        marker = support_dir() / "installed"
        if marker.is_symlink():
            raise CueError("UNSAFE_PATH")
        enabled = marker.is_file()
    # IINA's utils.exec keeps only LC_ALL. Path.home() still resolves, and
    # libraries and the supervised child need HOME in the environment.
    if enabled and not os.environ.get("HOME"):
        os.environ["HOME"] = str(Path.home())
    return enabled

def runtime_root() -> Path:
    override = os.environ.get("CUE_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if installed_mode():
        return support_dir()
    return (PROJECT / ".runtime").resolve()

def models_root() -> Path:
    override = os.environ.get("CUE_MODELS", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if installed_mode():
        return support_dir() / "models"
    return (PROJECT / ".runtime" / "models").resolve()

def runtime_tree() -> Path:
    root = support_dir() / "runtime"
    if root.is_symlink() or (root / "bin").is_symlink():
        raise CueError("UNSAFE_PATH")
    return root

def bundled_bin_dir() -> Path:
    return runtime_tree() / "bin"

def vad_model_path() -> Path:
    # Installed Cue ships the model inside its notarized runtime. A checkout
    # keeps the copy scripts/fetch-vad verified, beside its other runtime files.
    if installed_mode():
        return runtime_tree() / "vad" / "silero_vad.onnx"
    return runtime_root() / "vad" / "silero_vad.onnx"

def model_manifest_path() -> Path:
    # Development keeps the checkout file so profile hashes do not change.
    # An installed runtime carries its own copy; parents[3] is not the checkout.
    if not installed_mode():
        return (PROJECT / "models" / "manifest.json").resolve()
    path = runtime_tree() / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise CueError("SETUP_REQUIRED", "model manifest unavailable")
    return path.resolve()

def connection(root: Path):
    path = root/"connection.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise CueError("HELPER_DISCONNECTED")
    conn = json.loads(path.read_text())
    if conn.get("host") != "127.0.0.1" or conn.get("protocol_version") != 1:
        raise CueError("PROTOCOL_MISMATCH")
    return conn

def call(conn: dict, path: str, body=None, client=None, method=None):
    headers = {"Authorization": "Bearer "+conn["token"], "Content-Type": "application/json"}
    if client: headers["X-Cue-Client"] = client
    req = urllib.request.Request(f"http://127.0.0.1:{conn['port']}/v1{path}", data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as r: result = json.load(r)
    if result["instance_id"] != conn["instance_id"]: raise CueError("HELPER_DISCONNECTED")
    return result

def ensure(root: Path):
    if installed_mode():
        model_manifest_path()
    private_dir(root)
    lock_path = root/"bootstrap.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            conn = connection(root)
            health = call(conn, "/health")
        except (CueError, OSError, ValueError):
            conn = None
        if conn:
            if health.get("helper_version") == HELPER_VERSION: return conn
            try:
                call(conn, "/shutdown", {})
            except urllib.error.HTTPError as exc:
                raise CueError("HELPER_RESTART_REQUIRED", "wait for remux or close other Cue windows before upgrading the helper") from exc
            for _ in range(50):
                try: call(conn, "/health")
                except (CueError, OSError, ValueError): break
                time.sleep(.1)
            else:
                raise CueError("HELPER_RESTART_REQUIRED", "old helper did not stop")
        log_path = root/"helper.log"
        if log_path.is_symlink(): raise CueError("UNSAFE_PATH")
        if log_path.exists() and log_path.stat().st_size > 5*1024*1024:
            os.replace(log_path, root/"helper.previous.log")
        with log_path.open("ab") as log:
            log_path.chmod(0o600)
            process = subprocess.Popen([sys.executable, "-m", "cue.cli", "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True, env={**os.environ, "CUE_HOME": str(root)})
        until = time.monotonic()+10
        while time.monotonic() < until:
            if process.poll() is not None: raise CueError("HELPER_DISCONNECTED", "supervisor exited")
            try:
                conn = connection(root)
                if call(conn, "/health").get("helper_version") == HELPER_VERSION: return conn
            except (CueError, OSError, ValueError): time.sleep(.1)
        process.terminate()
        raise CueError("HELPER_DISCONNECTED", "bootstrap timeout")
