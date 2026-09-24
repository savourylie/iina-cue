import hashlib
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from cue.bootstrap import PROJECT
from cue.core import CueError
from cue.service import Supervisor

BODY = b"hello setup file!!"


def manifest_for(body: bytes) -> dict:
    return {"schema_version": 1, "assets": [{
        "name": "gemma", "repository": "example/gemma", "revision": "pinned", "folder": "gemma",
        "files": [{"path": "model.bin", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "git_blob": None}],
    }]}


class _State:
    def __init__(self, body: bytes, mode: str):
        self.body, self.mode, self.hits = body, mode, []
        self.once = False


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        state = self.server.state
        requested = self.headers.get("Range")
        state.hits.append(requested)
        body = b"x" * len(state.body) if state.mode == "corrupt" else state.body
        if state.mode == "flaky" and not state.once:
            state.once = True
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        start = 0
        status = 200
        if requested:
            start = int(requested.split("=", 1)[1].split("-", 1)[0])
            status = 206
        chunk = body[start:]
        if state.mode == "interrupt" and not state.once:
            state.once = True
            chunk = body[start:start + 4]
        self.send_response(status)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{start + len(chunk) - 1}/{len(body)}")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)

    def log_message(self, fmt, *args):
        return


def serve(body: bytes, mode: str):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.state = _State(body, mode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def bind(monkeypatch, tmp_path, body, mode):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest_for(body)))
    server = serve(body, mode)
    monkeypatch.setattr("cue.bootstrap.model_manifest_path", lambda: path)
    monkeypatch.setattr("cue.setupflow.source_url", lambda repository, revision, relative: f"http://127.0.0.1:{server.server_port}/{relative}")
    monkeypatch.setattr("cue.setupflow.pause", lambda seconds: None)
    supervisor = Supervisor(tmp_path / "runtime", tmp_path / "models", clock=lambda: 100)
    return supervisor, server


def wait_done(supervisor):
    last = None
    for _ in range(100):
        last = supervisor.request("GET", "/v1/setup", {}, None)
        if last["progress"]["phase"] in {"idle", "error", "cancelled"} and not (supervisor.setup_api()._thread and supervisor.setup_api()._thread.is_alive()):
            return last
        time.sleep(0.02)
    return last


def test_get_setup_reports_assets_space_sources_and_progress(monkeypatch, tmp_path):
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "full")
    try:
        body = supervisor.request("GET", "/v1/setup", {}, None)
    finally:
        server.shutdown()
    assert body["assets"][0]["files"][0]["state"] == "missing"
    assert body["bytes_needed"] == len(BODY)
    assert isinstance(body["free_disk_bytes"], int) and body["free_disk_bytes"] > 0
    assert body["sources"] == ["https://huggingface.co/example/gemma/tree/pinned"]
    assert body["progress"]["bytes_total"] == len(BODY)
    assert server.state.hits == []


def test_interrupted_download_resumes_with_http_range(monkeypatch, tmp_path):
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "interrupt")
    try:
        supervisor.request("POST", "/v1/setup/actions", {"action": "start"}, None)
        body = wait_done(supervisor)
    finally:
        server.shutdown()
    assert body["files_ready"] is True
    assert any(hit and hit.startswith("bytes=") for hit in server.state.hits)
    assert (tmp_path / "models" / "gemma" / "model.bin").read_bytes() == BODY


def test_restart_resumes_partial_instead_of_starting_over(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest_for(BODY)))
    partial = tmp_path / "models" / "gemma" / "model.bin.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(BODY[:4])
    monkeypatch.setattr("cue.bootstrap.model_manifest_path", lambda: path)
    first = Supervisor(tmp_path / "runtime", tmp_path / "models", clock=lambda: 100)
    seen = first.request("GET", "/v1/setup", {}, None)
    assert seen["assets"][0]["files"][0]["state"] == "partial"
    assert seen["progress"]["bytes_done"] == 4
    assert seen["bytes_needed"] == len(BODY) - 4
    server = serve(BODY, "full")
    monkeypatch.setattr("cue.setupflow.source_url", lambda repository, revision, relative: f"http://127.0.0.1:{server.server_port}/{relative}")
    monkeypatch.setattr("cue.setupflow.pause", lambda seconds: None)
    second = Supervisor(tmp_path / "runtime", tmp_path / "models", clock=lambda: 100)
    try:
        second.request("POST", "/v1/setup/actions", {"action": "resume"}, None)
        body = wait_done(second)
    finally:
        server.shutdown()
    assert server.state.hits[0] == "bytes=4-"
    assert body["files_ready"] is True
    assert (tmp_path / "models" / "gemma" / "model.bin").read_bytes() == BODY


def test_corrupt_bytes_are_not_moved_into_place(monkeypatch, tmp_path):
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "corrupt")
    try:
        supervisor.request("POST", "/v1/setup/actions", {"action": "start"}, None)
        body = wait_done(supervisor)
    finally:
        server.shutdown()
    assert body["progress"]["phase"] == "error"
    assert body["progress"]["error"]["detail"] == "checksum mismatch"
    assert not (tmp_path / "models" / "gemma" / "model.bin").exists()


def test_disk_refusal_names_the_exact_bytes_needed(monkeypatch, tmp_path):
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "full")
    monkeypatch.setattr("cue.setupflow.disk_free", lambda path: 0)
    try:
        with pytest.raises(CueError) as exc:
            supervisor.request("POST", "/v1/setup/actions", {"action": "start"}, None)
    finally:
        server.shutdown()
    assert exc.value.code == "DISK_FULL"
    assert str(exc.value) == str(len(BODY))
    assert server.state.hits == []


def test_transient_server_error_is_retried_with_backoff(monkeypatch, tmp_path):
    delays = []
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "flaky")
    monkeypatch.setattr("cue.setupflow.pause", lambda seconds: delays.append(seconds))
    try:
        supervisor.request("POST", "/v1/setup/actions", {"action": "start"}, None)
        body = wait_done(supervisor)
    finally:
        server.shutdown()
    assert delays and delays[0] == 0.5
    assert body["files_ready"] is True


def test_unknown_action_is_refused_and_runs_no_command(monkeypatch, tmp_path):
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "full")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("command")))
    try:
        with pytest.raises(CueError) as exc:
            supervisor.request("POST", "/v1/setup/actions", {"action": "bash", "command": "rm -rf /"}, None)
    finally:
        server.shutdown()
    assert exc.value.code == "INVALID_REQUEST"
    assert server.state.hits == []


def test_smoke_reports_failure_with_a_reason_without_models(monkeypatch, tmp_path):
    supervisor, server = bind(monkeypatch, tmp_path, BODY, "full")
    try:
        body = supervisor.request("POST", "/v1/setup/actions", {"action": "smoke"}, None)
    finally:
        server.shutdown()
    assert body["smoke"]["passed"] is False
    assert body["smoke"]["reason"] == "models are not installed"
    assert (tmp_path / "smoke-clip.wav").is_file()
    assert server.state.hits == []


def test_development_manifest_stays_the_pinned_file():
    text = (PROJECT / "models" / "manifest.json").read_text()
    assert "litert-community/gemma-4-E2B-it-litert-lm" in text
    assert "mlx-community/Qwen3-ForcedAligner-0.6B-4bit" in text
