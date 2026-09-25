"""One supervisor, one persistent inference process, authenticated short requests."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import multiprocessing as mp
from pathlib import Path
import queue
import secrets
import threading
import time
from urllib.parse import parse_qs
from .core import Cue, CueError, Settings, continuous_end, digest, next_window, ranges_merge, srt
from .bootstrap import HELPER_VERSION, model_manifest_path
from .media import Media, installed_ffmpeg_record
from .pipeline import worker_entry
from .remux import remux, validate_destination
from .storage import Cache, atomic_write, private_dir

def opaque() -> str: return secrets.token_hex(16)

def integer(value, lower=0, upper=10**12):
    if type(value) is not int or not lower <= value <= upper: raise CueError("INVALID_REQUEST")
    return value

@dataclass
class Session:
    id: str
    client: str
    media: Media
    settings: Settings
    source_profile: str
    profile: str
    position: int
    epoch: int = 0
    seq: int = 0
    rate: float = 1
    revision: int = 0
    installed_revision: int = 0
    installed: list = field(default_factory=list)
    prepared: list = field(default_factory=list)
    artifact: dict | None = None
    state: str = "preparing"
    error: dict | None = None
    language: dict = field(default_factory=lambda: {"code": "und", "status": "unknown"})
    timings: dict = field(default_factory=dict)
    last_seen: float = field(default_factory=time.monotonic)
    seek_at: float = 0
    versions: dict = field(default_factory=dict)
    retry_window: list[int] | None = None
    skipped_language: list[list[int]] = field(default_factory=list)

class Supervisor:
    def __init__(self, root: Path, models: Path, clock=time.monotonic):
        self.root, self.models, self.clock = private_dir(root), models, clock
        self.cache = Cache(root / "cache")
        self.instance, self.token = opaque(), secrets.token_hex(32)
        self.clients: dict[str, float] = {}
        self.sessions: dict[str, Session] = {}
        self.requests = {}
        self.remux_jobs: dict[str, dict] = {}
        self.remux_cancels: dict[str, threading.Event] = {}
        self.active = None
        self.busy = None
        self.worker = None
        self.inbox = self.outbox = None
        self.lock = threading.RLock()
        self.stopping = False
        self.started = self.clock()
        self.last_job = self.clock()
        self.manifest_hash = digest(json.loads(model_manifest_path().read_text()))
        self._setup = None
        self.smoking = False

    def setup_api(self):
        if self._setup is None:
            from . import bootstrap
            from .setupflow import Setup
            self._setup = Setup(self.models, bootstrap.model_manifest_path(), run_job=self.run_setup_job)
        return self._setup

    def run_setup_job(self, job: dict, timeout: float = 300) -> dict:
        """Run the setup smoke job on the same persistent worker captions use.
        Setup comes before captions, so a busy worker or a live session refuses it."""
        with self.lock:
            if self.busy or self.sessions or self.smoking:
                raise CueError("SETUP_BUSY", "close Cue in other windows, then retry")
            self.smoking = True
            self.start_worker()
            inbox, outbox, worker = self.inbox, self.outbox, self.worker
        try:
            inbox.put(job, timeout=5)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    message = outbox.get(timeout=1)
                except queue.Empty:
                    if not worker.is_alive():
                        raise CueError("WORKER_FAILED", "the inference worker stopped")
                    continue
                if message.get("job_id") == job["job_id"] and "stage" not in message:
                    return message
            with self.lock:
                self.stop_worker()
            raise CueError("WORKER_FAILED", "the smoke test timed out")
        finally:
            with self.lock:
                self.smoking = False
                self.last_job = self.clock()

    def start_worker(self):
        if self.worker and self.worker.is_alive(): return
        ctx = mp.get_context("spawn")
        self.inbox, self.outbox = ctx.Queue(maxsize=1), ctx.Queue(maxsize=16)
        self.worker = ctx.Process(target=worker_entry, args=(self.inbox, self.outbox, str(self.models), str(self.root/"audio-temp")), daemon=True)
        self.worker.start()

    def stop_worker(self):
        if self.worker:
            if self.worker.is_alive():
                try: self.inbox.put_nowait(None)
                except queue.Full: pass
                self.worker.join(timeout=1)
                if self.worker.is_alive(): self.worker.terminate(); self.worker.join(timeout=2)
                if self.worker.is_alive(): self.worker.kill(); self.worker.join(timeout=1)
            self.worker = None
        self.busy = None

    def publish(self, s: Session):
        ranges, cues, language = self.cache.read(s.profile)
        if ranges == s.prepared and s.artifact is not None: return
        content = srt(cues)
        path = self.root / "sessions" / s.id / "snapshot.srt"
        atomic_write(path, content)
        s.revision += 1
        s.prepared, s.language = ranges, language
        s.artifact = {"path": str(path), "sha256": hashlib.sha256(content.encode()).hexdigest(), "revision": s.revision,
                      "cue_count": len(cues), "complete_movie": ranges == [[0, s.media.duration_ms]]}
        s.versions[s.revision] = {"ranges": ranges, "sha256": s.artifact["sha256"], "epoch": s.epoch}
        s.versions = dict(list(s.versions.items())[-8:])

    def snapshot(self, s: Session):
        buffer = continuous_end(s.installed, s.position)-s.position
        job = self.busy if self.busy and self.busy["session"] == s.id and self.busy["epoch"] == s.epoch and self.busy["profile"] == s.profile else None
        return {"session_id": s.id, "seek_epoch": s.epoch, "profile_revision": 1, "snapshot_revision": s.revision,
                "state": s.state, "stage": job.get("stage", "extracting") if job else "idle",
                "stage_elapsed_s": round(self.clock()-job.get("stage_at", job["started"]), 1) if job else 0,
                "prepared_ranges": s.prepared, "installed_ranges": s.installed, "artifact": s.artifact,
                "skipped_language_ranges": s.skipped_language,
                "buffer_media_ms": buffer, "buffer_wall_ms": buffer/s.rate,
                "language": s.language, "metrics": s.timings, "error": s.error,
                "duration_ms": s.media.duration_ms, "target": s.settings.target,
                "ready": buffer >= min(s.settings.startup_ms, s.media.duration_ms-s.position)}

    def tick(self):
        with self.lock:
            now = self.clock()
            # The setup smoke job owns the worker's queues until it replies.
            if self.smoking: return
            for cid in list(self.clients):
                if now-self.clients[cid] > 45: self.remove_client(cid)
            for sid in list(self.sessions):
                if now-self.sessions[sid].last_seen > 45: del self.sessions[sid]
            if self.busy:
                response = None
                while True:
                    try: message = self.outbox.get_nowait()
                    except queue.Empty: break
                    if message["job_id"] != self.busy["job_id"]: continue
                    if "stage" not in message:
                        response = message; break
                    self.busy["stage"] = message["stage"]
                    self.busy["stage_at"] = now
                    current = self.sessions.get(self.busy["session"])
                    if current and current.epoch == self.busy["epoch"] and current.profile == self.busy["profile"] and "language" in message:
                        current.language = message["language"]
                if response:
                    job = self.busy; self.busy = None; self.last_job = now
                    s = self.sessions.get(job["session"])
                    if response["job_id"] != job["job_id"]: return
                    if "result" in response and job["media_obj"].unchanged():
                        r = response["result"]
                        committed = r.get("committed_range", job["range"])
                        self.cache.put(job["source_profile"], *committed, [Cue(**c) for c in r["source"]], r["language"])
                        self.cache.put(job["profile"], *committed, [Cue(**c) for c in r["rendered"]], r["language"])
                        if s and s.epoch == job["epoch"] and s.profile == job["profile"]:
                            s.timings = r["timings"]
                            try: self.publish(s); s.state = "running"
                            except CueError as exc: s.error = {"code": exc.code}; s.state = "error"
                    elif s and s.epoch == job["epoch"]:
                        failure = response.get("error", {"code": "SOURCE_CHANGED"})
                        if failure["code"] == "LANGUAGE_UNCERTAIN" and not job.get("attempt"):
                            a,b=job["range"]
                            s.retry_window=[a,min(s.media.duration_ms,a+min(24000,max(20000,2*(b-a))))]
                            s.state="preparing"
                        elif failure["code"] == "LANGUAGE_UNCERTAIN":
                            s.skipped_language = ranges_merge([*s.skipped_language, job["range"]])
                            s.state="preparing"
                        elif failure["code"] in {"ALIGNMENT_FAILED","ASR_FAILED"} and not job.get("attempt") and job["range"][1]-job["range"][0] >= 8000:
                            a,b=job["range"];s.retry_window=[a,a+(b-a)//2];s.state="preparing"
                        else:
                            s.error = failure; s.state = "error"
                elif not self.worker.is_alive() or now-self.busy["started"] > 180:
                    s = self.sessions.get(self.busy["session"])
                    if s: s.error = {"code": "WORKER_FAILED"}; s.state = "error"
                    self.stop_worker()
            if not self.sessions and self.worker and now-self.last_job > 600:
                self.stop_worker()
            if self.busy: return
            s = self.sessions.get(self.active)
            if not s or s.state == "error" or now-s.seek_at < .3: return
            if not s.media.unchanged(): s.error = {"code": "SOURCE_CHANGED"}; s.state = "error"; return
            try: self.publish(s)
            except CueError as exc: s.error = {"code": exc.code}; s.state = "error"; return
            retry = s.retry_window
            window = retry or next_window(ranges_merge([*s.prepared, *s.skipped_language]), s.position, s.media.duration_ms, s.settings, s.rate)
            if window is None: s.state = "idle"; return
            self.start_worker()
            job = {"job_id": opaque(), "session": s.id, "epoch": s.epoch, "source_profile": s.source_profile,
                   "profile": s.profile, "media": asdict(s.media), "settings": asdict(s.settings), "range": list(window), "attempt": 1 if retry else 0}
            s.retry_window = None
            if retry: job["settings"]["context_ms"] = max(s.settings.context_ms,2000)
            # Reuse a complete source chunk even when a new target/session starts
            # in its middle. Re-aligning a prefix would create conflicting cache
            # partitions for the same source profile.
            row = self.cache.db.execute("SELECT start,end,payload FROM chunks WHERE profile=? AND start<=? AND end>? ORDER BY start DESC LIMIT 1", (s.source_profile, window[0], window[0])).fetchone()
            if row:
                job["range"] = [row[0],row[1]]
                job["cached_source"] = json.loads(row[2])
            else:
                following = self.cache.db.execute("SELECT start,payload FROM chunks WHERE profile=? AND start>? ORDER BY start LIMIT 1", (s.source_profile,window[0])).fetchone()
                if following and following[0] <= job["range"][1]:
                    job["range"][1] = following[0]
                    job["following_source"] = json.loads(following[1])["cues"]
            try:
                _, previous_source, _ = self.cache.read(s.source_profile)
            except CueError as exc:
                s.error = {"code":exc.code}; s.state = "error"; return
            job["previous_source"] = [asdict(c) for c in previous_source if c.end_ms <= job["range"][0]][-1:]
            self.inbox.put_nowait(job)
            self.busy = {**job, "started": now, "media_obj": s.media}
            s.state = "preparing"

    def remove_client(self, cid):
        self.clients.pop(cid, None)
        self.sessions = {sid: s for sid, s in self.sessions.items() if s.client != cid}
        self.requests = {key: sid for key, sid in self.requests.items() if key[0] != cid}

    def remux_running(self) -> bool:
        with self.lock:
            return any(job["state"] == "running" for job in self.remux_jobs.values())

    def start_remux(self, source: str, output: str) -> dict:
        # Validate before returning a job ID; the worker repeats validation
        # immediately before touching the file to catch intervening changes.
        validate_destination(source, output)
        if self.remux_running(): raise CueError("REMUX_ACTIVE")
        self.remux_jobs = dict(list(self.remux_jobs.items())[-16:])
        job_id = opaque()
        job = {"job_id": job_id, "state": "running", "phase": "starting", "progress_pct": None, "started": time.monotonic()}
        self.remux_jobs[job_id] = job
        cancel = self.remux_cancels[job_id] = threading.Event()
        def report(phase: str, percent: int | None):
            with self.lock:
                if job["state"] != "running": return
                job["phase"] = phase
                if percent is not None:
                    job["progress_pct"] = max(job["progress_pct"] or 0, min(99, max(0, percent)))
        def work():
            try:
                path = remux(source, output, report, cancel)
                update = {"state": "complete", "phase": "complete", "progress_pct": 100, "path": path}
            except CueError as exc:
                if exc.code == "REMUX_CANCELLED": update = {"state": "cancelled", "phase": "cancelled"}
                else: update = {"state": "error", "phase": "error", "error": {"code": exc.code}}
            except Exception:
                update = {"state": "error", "phase": "error", "error": {"code": "REMUX_FAILED"}}
            with self.lock:
                job.update(update)
                self.remux_cancels.pop(job_id, None)
        threading.Thread(target=work, name="cue-remux", daemon=False).start()
        return {"job_id": job_id, "state": "running", "phase": "starting", "progress_pct": None}

    def request(self, method: str, path: str, body: dict, client: str | None):
        # Model identity is hashed outside the request lock and then remembered.
        if path == "/v1/setup" and method == "GET":
            return self.setup_api().status()
        if path == "/v1/setup/actions" and method == "POST":
            return self.setup_api().action(body)
        with self.lock:
            if path == "/v1/health" and method == "GET":
                return {"protocol_version": 1, "helper_version": HELPER_VERSION, "worker_busy": self.busy is not None}
            if path == "/v1/clients" and method == "POST":
                cid = opaque(); self.clients[cid] = self.clock(); return {"client_id": cid, "lease_seconds": 45}
            if path == "/v1/shutdown" and method == "POST":
                if self.remux_running(): raise CueError("REMUX_ACTIVE")
                if self.clients: raise CueError("CLIENTS_ACTIVE")
                self.stopping = True; return {"stopping": True}
            if client not in self.clients: raise CueError("CLIENT_REQUIRED")
            self.clients[client] = self.clock()
            if path == "/v1/heartbeat" and method == "POST": return {"ok": True, "sessions": [s.id for s in self.sessions.values() if s.client == client]}
            if path == "/v1/client" and method == "DELETE": self.remove_client(client); return {"ok": True}
            if path == "/v1/cache/status" and method == "GET": return self.cache.status()
            if path == "/v1/remux" and method == "POST":
                source, output = body.get("source"), body.get("output")
                if not isinstance(source, str) or not isinstance(output, str): raise CueError("INVALID_REQUEST")
                return self.start_remux(source, output)
            if path.startswith("/v1/remux/") and path.endswith("/cancel") and method == "POST":
                job_id = path.removeprefix("/v1/remux/").removesuffix("/cancel")
                job = self.remux_jobs.get(job_id)
                if not job: raise CueError("NOT_FOUND")
                # A job already committing its output ignores the request and completes.
                if job["state"] == "running" and job_id in self.remux_cancels: self.remux_cancels[job_id].set()
                return {**job, "cancel_requested": job["state"] == "running", "elapsed_s": round(time.monotonic()-job["started"], 1)}
            if path.startswith("/v1/remux/") and method == "GET":
                job = self.remux_jobs.get(path.removeprefix("/v1/remux/"))
                if not job: raise CueError("NOT_FOUND")
                return {**job, "elapsed_s": round(time.monotonic()-job["started"], 1)}
            if path == "/v1/sessions" and method == "POST":
                request_id = str(body.get("request_id", ""))
                if not 1 <= len(request_id) <= 100: raise CueError("INVALID_REQUEST")
                key = (client, request_id)
                if key in self.requests and self.requests[key] in self.sessions:
                    return self.snapshot(self.sessions[self.requests[key]])
                if len(self.sessions) >= 8: raise CueError("RESOURCE_PRESSURE")
                settings = Settings(**body.get("settings", {}))
                media = Media.open(body["path"], body.get("track", {}))
                position = integer(body.get("position_ms", 0), upper=media.duration_ms)
                source_profile = digest([media.stream_key, self.manifest_hash, settings.source,
                                         settings.first_ms, settings.window_ms, settings.context_ms,
                                         "pipeline-v3" if settings.source == "auto" else "pipeline-v4-manual-asr",
                                         "sentence-cues-v3"])
                profile = digest([source_profile, settings.target, "translate-v2"])
                s = Session(opaque(), client, media, settings, source_profile, profile, position)
                self.cache.register(source_profile, media.signature, "original")
                self.cache.register(profile, media.signature, settings.target)
                self.sessions[s.id] = s; self.requests[key] = s.id; self.active = s.id
                self.publish(s)
                return self.snapshot(s)
            parts = path.split("/")
            if len(parts) < 4 or parts[:3] != ["", "v1", "sessions"]: raise CueError("NOT_FOUND")
            s = self.sessions.get(parts[3])
            if not s or s.client != client: raise CueError("NOT_FOUND")
            s.last_seen = self.clock()
            action = parts[4] if len(parts) == 5 else ""
            if method == "DELETE" and not action:
                del self.sessions[s.id]; return {"ok": True}
            if action == "snapshot" and method == "GET": return self.snapshot(s)
            if action == "playback" and method == "PUT":
                seq = integer(body["client_seq"], 1)
                if seq <= s.seq: raise CueError("STALE_SEQUENCE")
                epoch = integer(body["seek_epoch"])
                if epoch < s.epoch: raise CueError("STALE_EPOCH")
                rate = body.get("rate", 1)
                if not isinstance(rate, (int, float)) or not math.isfinite(rate) or not .1 <= rate <= 8: raise CueError("INVALID_REQUEST")
                position = integer(body["position_ms"], upper=s.media.duration_ms)
                if body.get("audio_delay_ms", 0) != 0: raise CueError("AUDIO_DELAY_UNSUPPORTED")
                if epoch != s.epoch:
                    s.retry_window = None
                    s.epoch = epoch; s.installed = []; s.installed_revision = 0
                    s.versions.clear(); s.artifact = None; s.seek_at = self.clock()
                    s.error = None; s.state = "preparing"; self.publish(s)
                s.seq, s.position, s.rate = seq, position, rate
                return self.snapshot(s)
            if action == "render-ack" and method == "POST":
                revision = integer(body["revision"])
                version = s.versions.get(revision)
                if body.get("seek_epoch") != s.epoch or not version or version["epoch"] != s.epoch or revision < s.installed_revision or body.get("sha256") != version["sha256"]:
                    print(json.dumps({"event":"stale_render_ack","revision":revision,"installed":s.installed_revision,
                        "epoch":s.epoch,"ack_epoch":body.get("seek_epoch"),"known_revision":version is not None,
                        "hash_match":bool(version and body.get("sha256")==version["sha256"])}),flush=True)
                    raise CueError("STALE_ACK")
                if body.get("success") is not True:
                    s.error = {"code": "SUBTITLE_INSTALL_FAILED"}; s.state = "error"
                else:
                    s.installed, s.installed_revision = version["ranges"], revision
                return self.snapshot(s)
            if action == "actions" and method == "POST":
                name = body.get("action")
                if name == "prioritize": self.active = s.id
                elif name == "retry": s.error = None; s.state = "preparing"; self.active = s.id
                else: raise CueError("INVALID_REQUEST")
                return self.snapshot(s)
            if action == "export" and method == "POST":
                output = Path(body["output"])
                if not output.is_absolute() or ".." in output.parts: raise CueError("UNSAFE_PATH")
                dest = self.cache.export(s.profile, s.media.duration_ms, output, {"target": s.settings.target, "source": s.settings.source, "model_manifest": self.manifest_hash})
                return {"path": str(dest)}
            raise CueError("NOT_FOUND")

class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, supervisor: Supervisor):
        self.supervisor = supervisor
        super().__init__(("127.0.0.1", 0), Handler)

class Handler(BaseHTTPRequestHandler):
    server: Server
    def log_message(self, *args): pass
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PUT(self): self.handle_request()
    def do_DELETE(self): self.handle_request()
    def handle_request(self):
        sup = self.server.supervisor
        code = 200
        try:
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or self.headers.get("Origin") or not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer "+sup.token):
                code = 403; raise CueError("UNAUTHORIZED")
            if self.headers.get("Transfer-Encoding"): raise CueError("INVALID_REQUEST")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 65536: raise CueError("INVALID_REQUEST")
            self.connection.settimeout(5)
            data = self.rfile.read(length)
            if self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
                data = parse_qs(data.decode(), strict_parsing=True).get("payload", ["{}"])[0]
            body = json.loads(data or "{}")
            if not isinstance(body, dict): raise CueError("INVALID_REQUEST")
            response = sup.request(self.command, self.path, body, self.headers.get("X-Cue-Client"))
        except CueError as exc:
            print(json.dumps({"event":"request_error","method":self.command,"action":self.path.rsplit('/',1)[-1],"code":exc.code}),flush=True)
            if code == 200: code = 404 if exc.code == "NOT_FOUND" else 400
            response = {"error": {"code": exc.code}}
            if str(exc) and str(exc) != exc.code:
                response["error"]["detail"] = str(exc)
        except (ValueError, KeyError, TypeError, OSError):
            code = 400; response = {"error": {"code": "INVALID_REQUEST"}}
        response["instance_id"] = sup.instance
        payload = json.dumps(response, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload))); self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError): pass

def serve(root: Path, models: Path):
    sup = Supervisor(root, models)
    server = Server(sup)
    connection = {"host": "127.0.0.1", "port": server.server_port, "token": sup.token,
                  "instance_id": sup.instance, "protocol_version": 1, "helper_version": HELPER_VERSION}
    atomic_write(root/"connection.json", json.dumps(connection))
    record = installed_ffmpeg_record()
    if record: print(json.dumps(record), flush=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    no_clients_at = time.monotonic()
    try:
        while not sup.stopping:
            sup.tick()
            if sup.clients or sup.remux_running(): no_clients_at = time.monotonic()
            elif time.monotonic()-no_clients_at > 60: break
            time.sleep(.1)
    finally:
        server.shutdown(); server.server_close(); sup.stop_worker()
        (root/"connection.json").unlink(missing_ok=True)
