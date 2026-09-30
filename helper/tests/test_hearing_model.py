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
