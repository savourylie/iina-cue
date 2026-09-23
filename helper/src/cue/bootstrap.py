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
HELPER_VERSION = "0.1.4"
def runtime_root() -> Path:
    return Path(os.environ.get("CUE_HOME", str(PROJECT / ".runtime"))).resolve()
def models_root() -> Path:
    return Path(os.environ.get("CUE_MODELS", str(PROJECT / ".runtime/models"))).resolve()

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
