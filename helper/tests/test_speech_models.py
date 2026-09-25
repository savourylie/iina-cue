import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
from cue import setupflow
from cue.bootstrap import PROJECT
from cue.core import CueError
from cue.media import Media
from cue.service import Supervisor

MODEL = b"a small stand-in for a larger speech model"
GiB = 2 ** 30


def catalog_manifest():
    item = lambda body, name: {"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "git_blob": None}
    return {"schema_version": 1,
            "assets": [{"name": "gemma", "repository": "x/e2b", "revision": "r2", "folder": "gemma", "files": [item(b"e2b", "gemma-4-E2B-it.litertlm")]}],
            "optional_assets": [{"name": "gemma-e4b", "repository": "x/e4b", "revision": "r4", "folder": "gemma-e4b", "files": [item(MODEL, "gemma-4-E4B-it.litertlm")]}],
            "speech_models": [{"id": "e2b", "asset": "gemma", "file": "gemma-4-E2B-it.litertlm", "min_ram_bytes": 16 * GiB},
                              {"id": "e4b", "asset": "gemma-e4b", "file": "gemma-4-E4B-it.litertlm", "min_ram_bytes": 16 * GiB, "cache_bytes": 1000}],
            "default_speech_model": "e2b"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", str(len(MODEL)))
        self.end_headers()
        self.wfile.write(MODEL)

    def log_message(self, fmt, *args):
        return


@pytest.fixture
def env(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(catalog_manifest()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.hits = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr("cue.bootstrap.model_manifest_path", lambda: path)
    monkeypatch.setattr("cue.service.model_manifest_path", lambda: path)
    monkeypatch.setattr("cue.setupflow.source_url", lambda repository, revision, relative: f"http://127.0.0.1:{server.server_port}/{revision}/{relative}")
    monkeypatch.setattr("cue.setupflow.pause", lambda seconds: None)
    monkeypatch.setattr("cue.setupflow.machine_memory", lambda: 32 * GiB)
    # Trials here stub the smoke run, so the macOS voice (over a second, more under load) is not needed.
    monkeypatch.setattr("cue.setupflow.write_speech", lambda path: path.write_bytes(b"clip"))
    models = tmp_path / "models"
    (models / "gemma").mkdir(parents=True)
    (models / "gemma" / "gemma-4-E2B-it.litertlm").write_bytes(b"e2b")
    sup = Supervisor(tmp_path / "runtime", models, clock=lambda: 100)
    yield sup, server, models
    server.shutdown()


def act(sup, action, model):
    return sup.request("POST", "/v1/setup/actions", {"action": action, "model": model}, None)


def wait_idle(sup):
    for _ in range(1000):
        thread = sup.setup_api()._thread
        if not (thread and thread.is_alive()):
            return sup.request("GET", "/v1/setup", {}, None)["speech_models"]
        time.sleep(0.01)
    raise AssertionError("setup thread did not finish")


def by_id(status, model):
    return next(m for m in status["models"] if m["id"] == model)


def test_the_shipped_catalog_pins_e4b_and_keeps_e2b_default():
    manifest = json.loads((PROJECT / "models" / "manifest.json").read_text())
    assert manifest["default_speech_model"] == "e2b"
    # 12B was measured and dropped: slower than E2B, and it captioned fewer lines.
    assert [m["id"] for m in manifest["speech_models"]] == ["e2b", "e4b"]
    optional = {a["name"]: a for a in manifest["optional_assets"]}
    assert optional["gemma-e4b"]["revision"] == "2eee7ac325f20eb8c9ac1d0e972f7c84663062da"
    assert optional["gemma-e4b"]["files"][0]["sha256"] == "0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0"
    assert set(optional) == {"gemma-e4b"}
    # First-run setup still downloads only E2B and the aligner.
    assert [a["name"] for a in manifest["assets"]] == ["gemma", "aligner"]


def test_status_lists_models_with_size_memory_and_selection(env):
    sup, _, _ = env
    status = sup.request("GET", "/v1/setup", {}, None)["speech_models"]
    assert status["selected"] == "e2b"
    e2b = by_id(status, "e2b")
    assert e2b["state"] == "installed" and e2b["selected"] is True and e2b["optional"] is False
    assert by_id(status, "e4b")["state"] == "missing" and by_id(status, "e4b")["optional"] is True
    assert by_id(status, "e4b")["bytes"] == len(MODEL) and by_id(status, "e4b")["fits_memory"] is True
    assert by_id(status, "e4b")["disk_bytes"] == len(MODEL) + 1000, "disk needed counts the compile cache"


def test_e2b_is_not_downloaded_or_removed_here(env):
    sup, server, _ = env
    for action in ("model_download", "model_remove"):
        with pytest.raises(CueError) as exc:
            act(sup, action, "e2b")
        assert exc.value.code == "INVALID_REQUEST"
    with pytest.raises(CueError):
        act(sup, "model_download", "no-such-model")
    assert server.hits == []


def test_a_mac_without_enough_memory_cannot_download_or_use_a_model(env, monkeypatch):
    sup, server, _ = env
    monkeypatch.setattr("cue.setupflow.machine_memory", lambda: 8 * GiB)
    assert by_id(sup.request("GET", "/v1/setup", {}, None)["speech_models"], "e4b")["fits_memory"] is False
    for action in ("model_download", "model_use"):
        with pytest.raises(CueError) as exc:
            act(sup, action, "e4b")
        assert exc.value.code == "LOW_MEMORY"
    assert server.hits == []


def test_a_download_needs_room_for_the_model_and_its_compile_cache(env, monkeypatch):
    sup, server, _ = env
    monkeypatch.setattr("cue.setupflow.disk_free", lambda path: len(MODEL) + 999)
    with pytest.raises(CueError) as exc:
        act(sup, "model_download", "e4b")
    assert exc.value.code == "DISK_FULL" and str(exc.value) == str(len(MODEL) + 1000)
    assert server.hits == []


def test_download_is_verified_and_an_unchanged_file_is_not_hashed_again(env, monkeypatch):
    sup, server, models = env
    act(sup, "model_download", "e4b")
    status = wait_idle(sup)
    assert by_id(status, "e4b")["state"] == "installed"
    assert status["download"]["phase"] == "idle"
    assert (models / "gemma-e4b" / "gemma-4-E4B-it.litertlm").read_bytes() == MODEL
    assert server.hits == ["/r4/gemma-4-E4B-it.litertlm"]
    setupflow._verified.clear()
    monkeypatch.setattr("cue.setupflow._digest_matches", lambda path, item: (_ for _ in ()).throw(AssertionError("hashed again")))
    assert by_id(sup.request("GET", "/v1/setup", {}, None)["speech_models"], "e4b")["state"] == "installed"


def test_a_model_is_used_only_after_its_trial_passes(env, monkeypatch):
    sup, _, models = env
    with pytest.raises(CueError) as exc:
        act(sup, "model_use", "e4b")
    assert exc.value.code == "MODEL_NOT_INSTALLED"
    act(sup, "model_download", "e4b"); wait_idle(sup)
    tried = []
    monkeypatch.setattr("cue.setupflow._run_smoke", lambda clip, run_job: tried.append(sup.speech_model) or {"passed": True, "reason": "ok", "seconds": 2.0})
    monkeypatch.setattr(sup, "stop_worker", lambda: None)
    act(sup, "model_use", "e4b")
    status = wait_idle(sup)
    assert tried == ["e4b"]
    assert status["trial"]["phase"] == "passed" and status["selected"] == "e4b"
    assert json.loads((models / ".speech-model.json").read_text()) == {"model": "e4b"}
    # And back to the default the same way.
    act(sup, "model_use", "e2b")
    status = wait_idle(sup)
    assert tried == ["e4b", "e2b"] and status["selected"] == "e2b"
    assert json.loads((models / ".speech-model.json").read_text()) == {"model": "e2b"}


def test_a_failed_trial_goes_back_to_the_previous_model(env, monkeypatch):
    sup, _, models = env
    act(sup, "model_download", "e4b"); wait_idle(sup)
    monkeypatch.setattr("cue.setupflow._run_smoke", lambda clip, run_job: {"passed": False, "reason": "no subtitles"})
    monkeypatch.setattr(sup, "stop_worker", lambda: None)
    act(sup, "model_use", "e4b")
    status = wait_idle(sup)
    assert status["trial"] == {"model": "e4b", "phase": "failed", "reason": "no subtitles", "seconds": None}
    assert status["selected"] == "e2b" and not (models / ".speech-model.json").exists()


def test_a_trial_is_refused_while_captions_use_the_worker(env):
    sup, _, _ = env
    sup.busy = {"job_id": "caption"}
    with pytest.raises(CueError) as exc:
        sup.try_speech_model("e4b", Path("/unused.wav"))
    assert exc.value.code == "SETUP_BUSY" and sup.speech_model == "e2b"


def test_no_session_starts_while_a_model_is_on_trial(env, monkeypatch):
    sup, _, _ = env
    media = Media("/fixture.mp4", "signature", 1, "stream", 60000, 0, 1, 1)
    monkeypatch.setattr("cue.service.Media.open", lambda path, track: media)
    monkeypatch.setattr(sup, "stop_worker", lambda: None)
    sup.clients["a"] = 100
    refused = []
    def smoke(clip, run_job):
        # Another IINA window turns captions on mid-trial.
        with pytest.raises(CueError) as exc:
            sup.request("POST", "/v1/sessions", {"request_id": "late", "path": "/fixture.mp4"}, "a")
        refused.append(exc.value.code)
        return {"passed": False, "reason": "no subtitles"}
    monkeypatch.setattr("cue.setupflow._run_smoke", smoke)
    sup.try_speech_model("e4b", Path("/unused.wav"))
    assert refused == ["MODEL_SWITCHING"] and sup.sessions == {}
    assert sup.speech_model == "e2b" and sup.switching_model is False
    sup.request("POST", "/v1/sessions", {"request_id": "after", "path": "/fixture.mp4"}, "a")
    assert len(sup.sessions) == 1


def test_the_model_in_use_cannot_be_removed_but_another_can(env, monkeypatch):
    sup, _, models = env
    act(sup, "model_download", "e4b"); wait_idle(sup)
    sup.speech_model = "e4b"
    with pytest.raises(CueError) as exc:
        act(sup, "model_remove", "e4b")
    assert exc.value.code == "MODEL_IN_USE"
    sup.speech_model = "e2b"
    compiled = models / "compiled"
    compiled.mkdir()
    (compiled / "gemma-4-E4B-it.litertlm_1790329260_42_mldrift_weight_cache.bin").write_bytes(b"cache")
    (compiled / "gemma-4-E4B-it.litertlm_1790329260_42.audio_adapter.xnnpack_cache").write_bytes(b"cache")
    (compiled / "gemma-4-E2B-it.litertlm_1790157460_7_mldrift_weight_cache.bin").write_bytes(b"cache")
    act(sup, "model_remove", "e4b")
    assert not (models / "gemma-e4b" / "gemma-4-E4B-it.litertlm").exists()
    # Its compile cache goes too; the model still in use keeps its own.
    assert [p.name for p in compiled.iterdir()] == ["gemma-4-E2B-it.litertlm_1790157460_7_mldrift_weight_cache.bin"]
    assert "gemma-e4b/gemma-4-E4B-it.litertlm" not in json.loads((models / ".verified.json").read_text())
    assert by_id(sup.request("GET", "/v1/setup", {}, None)["speech_models"], "e4b")["state"] == "missing"


def test_the_speech_model_is_part_of_the_cache_key(env, monkeypatch):
    sup, _, _ = env
    media = Media("/fixture.mp4", "signature", 1, "stream", 60000, 0, 1, 1)
    monkeypatch.setattr("cue.service.Media.open", lambda path, track: media)
    sup.clients["a"] = 100
    sup.request("POST", "/v1/sessions", {"request_id": "one", "path": "/fixture.mp4"}, "a")
    sup.speech_model = "e4b"
    sup.request("POST", "/v1/sessions", {"request_id": "two", "path": "/fixture.mp4"}, "a")
    assert len({s.source_profile for s in sup.sessions.values()}) == 2


def test_catalog_figures_do_not_change_the_cache_key(env, monkeypatch, tmp_path):
    sup, _, _ = env
    media = Media("/fixture.mp4", "signature", 1, "stream", 60000, 0, 1, 1)
    monkeypatch.setattr("cue.service.Media.open", lambda path, track: media)
    sup.clients["a"] = 100
    before = sup.request("POST", "/v1/sessions", {"request_id": "one", "path": "/fixture.mp4"}, "a")
    manifest = catalog_manifest()
    manifest["speech_models"][1]["min_ram_bytes"] = 24 * GiB
    manifest["speech_models"][1]["cache_bytes"] = 5
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    again = Supervisor(tmp_path / "runtime2", sup.models, clock=lambda: 100)
    again.clients["a"] = 100
    after = again.request("POST", "/v1/sessions", {"request_id": "one", "path": "/fixture.mp4"}, "a")
    profile = lambda s, snap: s.sessions[snap["session_id"]].source_profile
    assert profile(sup, before) == profile(again, after)


def test_a_chosen_model_whose_file_is_gone_or_cut_short_falls_back_to_e2b(env, tmp_path):
    sup, _, models = env
    (models / ".speech-model.json").write_text(json.dumps({"model": "e4b"}))
    again = Supervisor(tmp_path / "runtime2", models, clock=lambda: 100)
    assert again.speech_model == "e2b"
    (models / "gemma-e4b").mkdir()
    (models / "gemma-e4b" / "gemma-4-E4B-it.litertlm").write_bytes(MODEL[:-1])
    assert Supervisor(tmp_path / "runtime3", models, clock=lambda: 100).speech_model == "e2b"
    (models / "gemma-e4b" / "gemma-4-E4B-it.litertlm").write_bytes(MODEL)
    assert Supervisor(tmp_path / "runtime4", models, clock=lambda: 100).speech_model == "e4b"
    # A model dropped from the catalog, as 12B was, is no longer a choice.
    (models / ".speech-model.json").write_text(json.dumps({"model": "12b"}))
    assert Supervisor(tmp_path / "runtime5", models, clock=lambda: 100).speech_model == "e2b"


def test_the_worker_starts_with_the_selected_model(env, monkeypatch):
    sup, _, models = env
    started = {}
    class FakeProcess:
        def __init__(self, target, args, daemon): started["args"] = args
        def start(self): pass
        def is_alive(self): return True
    class FakeContext:
        def Queue(self, maxsize): return object()
        def Process(self, target, args, daemon): return FakeProcess(target, args, daemon)
    monkeypatch.setattr("cue.service.mp.get_context", lambda name: FakeContext())
    sup.speech_model = "e4b"
    sup.start_worker()
    assert started["args"][-1] == str(models / "gemma-e4b" / "gemma-4-E4B-it.litertlm")


def test_concurrent_marker_and_progress_writes_neither_fail_nor_lose_entries(tmp_path):
    # A download thread and status requests on the helper's HTTP threads write these files at once.
    models = tmp_path / "models"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(catalog_manifest()))
    setup = setupflow.Setup(models, manifest)
    start, errors = threading.Barrier(32), []
    def write(i):
        start.wait()
        try:
            setupflow._save_markers(models, {f"file-{i}": [i]})
            setup._save(**{f"field_{i}": i})
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=write, args=(i,)) for i in range(32)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert errors == []
    assert set(json.loads((models / ".verified.json").read_text())) == {f"file-{i}" for i in range(32)}
    assert {f"field_{i}" for i in range(32)} <= set(json.loads((models / ".setup-progress.json").read_text()))
