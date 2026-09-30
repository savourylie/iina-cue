import json
from pathlib import Path
import pytest
from cue import setupflow
from cue.core import CueError

ROOT = Path(__file__).resolve().parents[2]


def real_manifest():
    return json.loads((ROOT / "models" / "manifest.json").read_text())


def test_the_manifest_names_whisper_as_the_hearing_engine_from_two_required_assets():
    manifest = real_manifest()
    hearing = manifest["hearing_model"]
    assert hearing["id"] == "whisper-turbo" and hearing["folder"] == "whisper-large-v3-turbo"
    required = {asset["name"]: asset for asset in manifest["assets"]}
    assert set(hearing["assets"]) == {"whisper-turbo", "whisper-turbo-processor"} <= required.keys()
    for name in hearing["assets"]:
        asset = required[name]
        assert asset["folder"] == hearing["folder"] and len(asset["revision"]) == 40
        for item in asset["files"]:
            assert item["bytes"] > 0 and (item["sha256"] or item["git_blob"])
    # openai's config.json would overwrite the MLX one; only the weights asset carries a config.
    assert [f["path"] for f in required["whisper-turbo"]["files"]] == ["config.json", "weights.safetensors"]
    assert "config.json" not in [f["path"] for f in required["whisper-turbo-processor"]["files"]]
    assert required["whisper-turbo"]["repository"] == "mlx-community/whisper-large-v3-turbo"
    assert required["whisper-turbo-processor"]["repository"] == "openai/whisper-large-v3-turbo"


def hearing_manifest():
    sha = lambda body: {"path": body[0], "bytes": body[1], "sha256": "c" * 64, "git_blob": None}
    return {"schema_version": 1,
            "assets": [{"name": "gemma", "repository": "x/e2b", "revision": "r2", "folder": "gemma",
                        "files": [{"path": "gemma-4-E2B-it.litertlm", "bytes": 3, "sha256": "0" * 64, "git_blob": None}]},
                       {"name": "whisper-turbo", "repository": "x/whisper", "revision": "a" * 40, "folder": "whisper-large-v3-turbo",
                        "files": [{"path": "config.json", "bytes": 2, "sha256": None, "git_blob": "b" * 40}, sha(("weights.safetensors", 4))]},
                       {"name": "whisper-turbo-processor", "repository": "x/openai", "revision": "d" * 40, "folder": "whisper-large-v3-turbo",
                        "files": [{"path": "tokenizer.json", "bytes": 5, "sha256": None, "git_blob": "e" * 40}]}],
            "hearing_model": {"id": "whisper-turbo", "assets": ["whisper-turbo", "whisper-turbo-processor"], "folder": "whisper-large-v3-turbo"}}


def install(models, manifest):
    for asset in manifest["assets"]:
        for item in asset["files"]:
            path = models / asset["folder"] / item["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * item["bytes"])


def test_hearing_model_helpers_resolve_the_folder_and_check_every_file_at_its_pinned_size(tmp_path):
    manifest = hearing_manifest(); models = tmp_path / "models"
    assert setupflow.hearing_model({"assets": []}) is None
    assert setupflow.hearing_model(manifest)["id"] == "whisper-turbo"
    assert setupflow.hearing_model_path(models, manifest) == models / "whisper-large-v3-turbo"
    with pytest.raises(CueError):
        setupflow.hearing_model_path(models, {"assets": []})
    assert setupflow.hearing_model_complete(models, manifest) is False
    install(models, manifest)
    assert setupflow.hearing_model_complete(models, manifest) is True
    weights = models / "whisper-large-v3-turbo" / "weights.safetensors"
    weights.write_bytes(b"xxx")                      # a partial download
    assert setupflow.hearing_model_complete(models, manifest) is False
    weights.write_bytes(b"xxxx")
    tokenizer = models / "whisper-large-v3-turbo" / "tokenizer.json"
    tokenizer.unlink(); tokenizer.symlink_to(weights)  # a symlink never counts
    assert setupflow.hearing_model_complete(models, manifest) is False
    assert setupflow.hearing_model_complete(models, {"assets": []}) is False


def test_the_supervisor_hears_with_the_manifest_engine_and_keys_the_cache_by_its_revision(tmp_path, monkeypatch):
    from cue.service import Supervisor
    manifest = hearing_manifest()
    path = tmp_path / "manifest.json"; path.write_text(json.dumps(manifest))
    monkeypatch.setattr("cue.service.model_manifest_path", lambda: path)
    monkeypatch.setattr("cue.bootstrap.model_manifest_path", lambda: path)
    models = tmp_path / "models"
    sup = Supervisor(tmp_path / "runtime", models, clock=lambda: 100)
    assert sup.asr == str(models / "whisper-large-v3-turbo")
    assert sup.asr_key() == "asr:whisper-turbo@" + "a" * 40
    sup.asr = str(tmp_path / "elsewhere" / "qwen3-asr-1.7b-4bit")   # the evaluation driver's override
    assert sup.asr_key() == "asr:qwen3-asr-1.7b-4bit"
    sup.asr = None
    assert sup.asr_key() == ""
    del manifest["hearing_model"]; path.write_text(json.dumps(manifest))
    assert Supervisor(tmp_path / "runtime2", models, clock=lambda: 100).asr is None


def test_doctor_reports_the_hearing_model_files(tmp_path, monkeypatch):
    from cue import doctor
    monkeypatch.setattr(doctor, "_vad_ready", lambda: True)
    models = tmp_path / "models"
    assert doctor.model_assets(models)["whisper-turbo"] is False
    folder = models / "whisper-large-v3-turbo"; folder.mkdir(parents=True)
    (folder / "weights.safetensors").write_bytes(b"w"); (folder / "tokenizer.json").write_text("{}")
    assert doctor.model_assets(models) == {"gemma": False, "aligner": False, "whisper-turbo": True, "vad": True}
