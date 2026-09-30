# Whisper Hearing Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cue hears with Whisper large-v3-turbo as a required first-run asset and translates with Gemma; no new setting, no new UI control.

**Architecture:** The manifest gains two required assets (MLX weights, openai processor files) and a `hearing_model` field; the supervisor resolves the engine's folder from the manifest at start and hands it to the existing `MlxAsr` worker path, keyed into the source cache by id and revision. Download, verification and the setup smoke are the existing ones. Docs, credits and licence notices follow.

**Tech Stack:** Python 3.12 helper (`helper/src/cue`), pytest, mlx_audio 0.4 (already a dependency), TypeScript plugin (`plugin/src`, node:test), `scripts/test` + `npm run build` as the gate.

**Spec:** `docs/superpowers/specs/2026-09-30-whisper-hearing-engine-design.md`

## Global Constraints

- Local seekable media only; no cloud in the product. Gemma 4 E2B stays the default translation model; E4B only by explicit choice in Advanced. Never substitute a model silently (a missing hearing model is `SETUP_REQUIRED`, never a fall-back to Gemma hearing).
- Source timestamps come from the Qwen forced aligner only.
- Model files are downloaded only after consent, from the repositories and revisions pinned in `models/manifest.json`, and verified by sha256 or git blob.
- Whisper weights: `mlx-community/whisper-large-v3-turbo` @ `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb`; processor files: `openai/whisper-large-v3-turbo` @ `41f01f3fe87f28c78e2fbf8b568835947dd65ed9`; folder `whisper-large-v3-turbo`; both MIT.
- Run `scripts/test` and `npm run build` before every commit; unit tests are not inference evidence.
- Fence asynchronous results by instance, session, seek epoch and profile; the source cache key includes the hearing engine's id and revision.
- No private media discovery; the only real media used are the films the user named.

## Review Focus

1. An install that already has a Gemma-hearing cache: after the update the source profile must change (manifest hash and `asr:<id>@<revision>`) so old transcripts are never served as Whisper's — Task 3's key test.
2. The hearing folder deleted after setup: a session must end with `SETUP_REQUIRED`, not hang or crash — Task 4's test.
3. openai's `config.json` must never land in the folder over the MLX one — Task 1's manifest test.
4. A partial or symlinked weights file must count as incomplete at helper start — Task 2's test.
5. The sidebar's i18n test walks every `data-i18n` key in `sidebar.html`; the new credit key must exist with matching English — Task 7 runs `scripts/test`.

## File Structure

- Modify `models/manifest.json` — two assets + `hearing_model`.
- Modify `scripts/setup-models` — licence wording.
- Modify `helper/src/cue/setupflow.py` — `hearing_model`, `hearing_model_path`, `hearing_model_complete`.
- Modify `helper/src/cue/service.py` — `Supervisor.asr` from the manifest, `asr_key` with revision.
- Modify `helper/src/cue/asr.py` — `SETUP_REQUIRED` on a missing engine.
- Modify `helper/src/cue/doctor.py` — `model_assets()` helper reporting Whisper.
- Modify `scripts/eval-session.py`, `scripts/probe-languages.py` — `--asr gemma|PATH`.
- Modify `plugin/sidebar.html`, `plugin/src/strings.ts`, `plugin/src/runtime-install.ts`, `plugin/tests/install-runtime.test.ts` — credit line.
- Create `third_party/license-overrides/mit.txt`, `third_party/license-overrides/models/whisper-large-v3-turbo/SOURCE.txt`; modify `scripts/collect_licenses.py`, `THIRD_PARTY_NOTICES.md`.
- Modify `README.md`, `docs/install-cue.md`, `docs/install.md`, `docs/troubleshooting.md`, `docs/acceptance.md`.
- Create `helper/tests/test_hearing_model.py`; modify `helper/tests/test_asr.py`, `helper/tests/test_collect_licenses.py`, `helper/tests/test_install_guide.py`.

---

### Task 1: Manifest names Whisper as the hearing engine

**Files:**
- Modify: `models/manifest.json`
- Modify: `scripts/setup-models:18`
- Test: `helper/tests/test_hearing_model.py`

**Interfaces:**
- Produces: manifest `assets` entries `whisper-turbo` and `whisper-turbo-processor` (folder `whisper-large-v3-turbo`), top-level `hearing_model = {"id": "whisper-turbo", "assets": ["whisper-turbo", "whisper-turbo-processor"], "folder": "whisper-large-v3-turbo"}`.

- [ ] **Step 1: Write the failing test**

```python
# helper/tests/test_hearing_model.py
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest helper/tests/test_hearing_model.py -q`
Expected: FAIL with `KeyError: 'hearing_model'`

- [ ] **Step 3: Add the assets and the field**

```bash
cd /Users/calvinku/FunProjects/iina-cue && .venv/bin/python - <<'EOF'
import json
from pathlib import Path
p = Path("models/manifest.json"); m = json.loads(p.read_text())
blob = lambda path, size, sha1: {"path": path, "bytes": size, "sha256": None, "git_blob": sha1}
m["assets"].append({"name": "whisper-turbo", "repository": "mlx-community/whisper-large-v3-turbo",
    "revision": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb", "folder": "whisper-large-v3-turbo",
    "files": [blob("config.json", 268, "6ac9a52a28f70a2e5681c250a470eca6e9c8cc3e"),
              {"path": "weights.safetensors", "bytes": 1613977612,
               "sha256": "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6",
               "git_blob": "26b12d9fb292a7bee72610f6e7e2ec84225feab7"}]})
m["assets"].append({"name": "whisper-turbo-processor", "repository": "openai/whisper-large-v3-turbo",
    "revision": "41f01f3fe87f28c78e2fbf8b568835947dd65ed9", "folder": "whisper-large-v3-turbo",
    "files": [blob("preprocessor_config.json", 340, "931c77a740890c46365c7ae0c9d350ba3cca908f"),
              blob("tokenizer.json", 2710337, "17456db595adc78a973f97d69d8cb50bc87c0b1c"),
              blob("tokenizer_config.json", 282843, "06ffdc8308eae6bb7bd1fdd81e94b0a881a539ab"),
              blob("special_tokens_map.json", 2186, "312bc106291bb51bf2cc1648df070bef963a0639"),
              blob("added_tokens.json", 34648, "1b33526d33aaa60d79f78ae8651dae50b730185a"),
              blob("normalizer.json", 52666, "dd6ae819ad738ac1a546e9f9282ef325c33b9ea0"),
              blob("vocab.json", 1036558, "0f3456460629e21d559c6daa23ab6ce3644e8271"),
              blob("merges.txt", 493869, "6038932a2a1f09a66991b1c2adae0d14066fa29e"),
              blob("generation_config.json", 3772, "cbe752958dc3e4671b0e0220aa1c545423a6d5f5")]})
m["hearing_model"] = {"id": "whisper-turbo", "assets": ["whisper-turbo", "whisper-turbo-processor"], "folder": "whisper-large-v3-turbo"}
p.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n")
EOF
sed -i '' 's/print("Pinned model cards declare Apache 2.0. Read THIRD_PARTY_NOTICES.md/print("Pinned model cards declare Apache 2.0 (Gemma, Qwen aligner) and MIT (Whisper). Read THIRD_PARTY_NOTICES.md/' scripts/setup-models
```

- [ ] **Step 4: Run the test and the whole suite**

Run: `.venv/bin/python -m pytest helper/tests -q`
Expected: all pass (the manifest test passes; `test_collect_licenses` still passes because `model_needles` looks up only the three Gemma/aligner names until Task 8).

- [ ] **Step 5: Verify the checkout's files match the pinned digests**

Run: `.venv/bin/python scripts/setup-models --accept-download 2>&1 | grep -c "Verified: whisper"`
Expected: `11` (the files already in `.runtime/models/whisper-large-v3-turbo` verify; nothing is downloaded).

- [ ] **Step 6: Commit**

```bash
git add models/manifest.json scripts/setup-models helper/tests/test_hearing_model.py
git commit -m "feat(models): Whisper large-v3-turbo is a required first-run asset and the hearing engine"
```

---

### Task 2: setupflow helpers for the hearing engine

**Files:**
- Modify: `helper/src/cue/setupflow.py` (after `speech_model_complete`, before `machine_memory`)
- Test: `helper/tests/test_hearing_model.py`

**Interfaces:**
- Consumes: `find_asset(manifest, name) -> (asset, optional)`, `destination(models, asset, item) -> Path` (existing).
- Produces: `hearing_model(manifest) -> dict | None`, `hearing_model_path(models, manifest) -> Path`, `hearing_model_complete(models, manifest) -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `helper/tests/test_hearing_model.py`)

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest helper/tests/test_hearing_model.py -q`
Expected: FAIL with `AttributeError: module 'cue.setupflow' has no attribute 'hearing_model'`

- [ ] **Step 3: Implement** (insert after `speech_model_complete` in `helper/src/cue/setupflow.py`)

```python
def hearing_model(manifest: dict) -> dict | None:
    """The dedicated hearing engine in front of Gemma, or None for a manifest without one."""
    return manifest.get("hearing_model")


def hearing_model_path(models: Path, manifest: dict) -> Path:
    choice = hearing_model(manifest)
    if choice is None:
        raise CueError("INVALID_REQUEST")
    return models / choice["folder"]


def hearing_model_complete(models: Path, manifest: dict) -> bool:
    """Every file of the engine's assets is in place at its pinned size. Hashes were checked
    at download time; this is the cheap check at every helper start, as for speech models."""
    choice = hearing_model(manifest)
    if choice is None:
        return False
    for name in choice["assets"]:
        asset, _ = find_asset(manifest, name)
        for item in asset["files"]:
            path = destination(models, asset, item)
            if path.is_symlink() or not path.is_file() or path.stat().st_size != item["bytes"]:
                return False
    return True
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest helper/tests/test_hearing_model.py helper/tests/test_setup.py helper/tests/test_speech_models.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add helper/src/cue/setupflow.py helper/tests/test_hearing_model.py
git commit -m "feat(helper): resolve the hearing engine's folder and completeness from the manifest"
```

---

### Task 3: The supervisor hears with the manifest engine and keys the cache by its revision

**Files:**
- Modify: `helper/src/cue/service.py` (the `self.asr` assignment in `Supervisor.__init__` and `asr_key`)
- Test: `helper/tests/test_hearing_model.py`

**Interfaces:**
- Consumes: `setupflow.hearing_model`, `hearing_model_path`, `find_asset`; `Supervisor._manifest()`.
- Produces: `Supervisor.asr: str | None` set at construction; `Supervisor.asr_key() -> str` = `asr:<id>@<revision>` for the manifest engine, `asr:<folder name>` for an override path, `""` for none.

- [ ] **Step 1: Write the failing test** (append to `helper/tests/test_hearing_model.py`)

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest helper/tests/test_hearing_model.py -q -k supervisor`
Expected: FAIL with `assert None == '.../models/whisper-large-v3-turbo'`

- [ ] **Step 3: Implement** in `helper/src/cue/service.py`

Replace

```python
        # Path of a dedicated speech-to-text model (asr.py) used in front of Gemma, or None. Set by
        # the evaluation driver for now; it is part of the source cache key.
        self.asr: str | None = None

    def asr_key(self) -> str:
        return f"asr:{Path(self.asr).name}" if self.asr else ""
```

with

```python
        # The dedicated hearing engine (asr.py) in front of Gemma: the manifest's, or None for a
        # manifest without one. The evaluation driver may replace it. Part of the source cache key.
        self.asr: str | None = self._manifest_hearing_path()

    def _manifest_hearing_path(self) -> str | None:
        from .setupflow import hearing_model, hearing_model_path
        manifest = self._manifest()
        return str(hearing_model_path(self.models, manifest)) if hearing_model(manifest) else None

    def asr_key(self) -> str:
        """Part of the cache key: transcripts from one hearing engine are never served as another's."""
        if not self.asr:
            return ""
        from .setupflow import find_asset, hearing_model
        manifest = self._manifest()
        choice = hearing_model(manifest)
        if choice and Path(self.asr) == self.models / choice["folder"]:
            return f"asr:{choice['id']}@{find_asset(manifest, choice['assets'][0])[0]['revision']}"
        return f"asr:{Path(self.asr).name}"
```

- [ ] **Step 4: Run the helper suite**

Run: `.venv/bin/python -m pytest helper/tests -q`
Expected: all pass. `test_speech_models.py::test_the_worker_starts_with_the_selected_model` still asserts `args[5] is None` because its catalog manifest has no `hearing_model`.

- [ ] **Step 5: Commit**

```bash
git add helper/src/cue/service.py helper/tests/test_hearing_model.py
git commit -m "feat(helper): the supervisor hears with the manifest's engine, keyed by id and revision"
```

---

### Task 4: A missing hearing model is SETUP_REQUIRED

**Files:**
- Modify: `helper/src/cue/asr.py` (`MlxAsr.load`)
- Test: `helper/tests/test_asr.py`

**Interfaces:**
- Produces: `MlxAsr.load()` raises `CueError("SETUP_REQUIRED")` when `<path>/config.json` is missing, `MODEL_LOAD_FAILED` for any other load error.

- [ ] **Step 1: Give the existing tests a real model folder and add the new one**

In `helper/tests/test_asr.py`, add after `FakeQwen`:

```python
def model_dir(tmp_path, name='qwen', family='qwen3_asr'):
    path=tmp_path/name; path.mkdir(exist_ok=True); (path/'config.json').write_text('{"model_type": "%s"}' % family); return path
```

then change every `MlxAsr(tmp_path/'qwen', ...)` to `MlxAsr(model_dir(tmp_path), ...)` and `MlxAsr(tmp_path/'whisper', loader=lambda path: fake, family='whisper')` to `MlxAsr(model_dir(tmp_path, 'whisper', 'whisper'), loader=lambda path: fake)` (the `family=` argument stays supported but the folder now says it). Append:

```python
def test_a_missing_hearing_model_is_setup_required_not_a_load_failure(tmp_path):
    with pytest.raises(CueError) as exc: MlxAsr(tmp_path/'whisper-large-v3-turbo', loader=lambda p: FakeQwen()).load()
    assert exc.value.code=='SETUP_REQUIRED'
    asr=MlxAsr(model_dir(tmp_path, 'whisper-large-v3-turbo', 'whisper'), loader=lambda p: FakeQwen()); asr.load()
    assert asr.model is not None and asr.family=='whisper'
```

- [ ] **Step 2: Run to see the new test fail**

Run: `.venv/bin/python -m pytest helper/tests/test_asr.py -q`
Expected: the new test FAILS (`asr.model` loads without a folder; no `SETUP_REQUIRED`); the others pass.

- [ ] **Step 3: Implement** in `helper/src/cue/asr.py`

```python
    def load(self) -> None:
        if self.model is not None:
            return
        if not (self.path / "config.json").is_file():
            # The engine is a pinned first-run asset: its absence is a setup state, never a
            # reason to hear with Gemma instead.
            raise CueError("SETUP_REQUIRED", f"hearing model missing: {self.path.name}")
        if self._loader is None:
            from mlx_audio.stt.utils import load_model
            self._loader = lambda path: load_model(str(path))
        try:
            self.model = self._loader(self.path)
        except Exception as exc:
            raise CueError("MODEL_LOAD_FAILED", type(exc).__name__) from exc
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest helper/tests/test_asr.py helper/tests/test_backend.py helper/tests/test_pipeline.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add helper/src/cue/asr.py helper/tests/test_asr.py
git commit -m "fix(helper): a missing hearing model is SETUP_REQUIRED, never a silent fall-back"
```

---

### Task 5: doctor reports the hearing model

**Files:**
- Modify: `helper/src/cue/doctor.py`
- Test: `helper/tests/test_hearing_model.py`

**Interfaces:**
- Produces: `doctor.model_assets(models: Path) -> dict` with keys `gemma`, `aligner`, `whisper-turbo`, `vad`; `doctor(models)` uses it.

- [ ] **Step 1: Write the failing test** (append to `helper/tests/test_hearing_model.py`)

```python
def test_doctor_reports_the_hearing_model_files(tmp_path, monkeypatch):
    from cue import doctor
    monkeypatch.setattr(doctor, "_vad_ready", lambda: True)
    models = tmp_path / "models"
    assert doctor.model_assets(models)["whisper-turbo"] is False
    folder = models / "whisper-large-v3-turbo"; folder.mkdir(parents=True)
    (folder / "weights.safetensors").write_bytes(b"w"); (folder / "tokenizer.json").write_text("{}")
    assert doctor.model_assets(models) == {"gemma": False, "aligner": False, "whisper-turbo": True, "vad": True}
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest helper/tests/test_hearing_model.py -q -k doctor`
Expected: FAIL with `AttributeError: module 'cue.doctor' has no attribute 'model_assets'`

- [ ] **Step 3: Implement** in `helper/src/cue/doctor.py`: add before `def doctor(`

```python
def model_assets(models: Path) -> dict:
    """Which pinned model files are in place; the hearing engine needs its weights and tokenizer."""
    whisper = models / "whisper-large-v3-turbo"
    return {"gemma": (models / "gemma/gemma-4-E2B-it.litertlm").is_file(),
            "aligner": (models / "aligner/model.safetensors").is_file(),
            "whisper-turbo": (whisper / "weights.safetensors").is_file() and (whisper / "tokenizer.json").is_file(),
            "vad": _vad_ready()}
```

and replace the inline dict in `doctor()`:

```python
            "model_assets": model_assets(models),
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest helper/tests/test_hearing_model.py helper/tests/test_bootstrap.py helper/tests/test_cli.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add helper/src/cue/doctor.py helper/tests/test_hearing_model.py
git commit -m "feat(helper): doctor reports the Whisper hearing model"
```

---

### Task 6: Evaluation tools can still hear with Gemma

**Files:**
- Modify: `scripts/eval-session.py:29-36`
- Modify: `scripts/probe-languages.py`

**Interfaces:**
- Produces: `--asr` unset → manifest engine; `--asr gemma` → `sup.asr = None`; `--asr PATH` → override. `probe-languages.py --asr gemma|PATH`, default = manifest engine.

- [ ] **Step 1: eval-session.py**

Replace the `--asr` argument and its handling:

```python
    ap.add_argument("--asr", help="hearing engine: unset = the manifest's (product behaviour); 'gemma' = Gemma's own hearing; or the path of an mlx_audio speech-to-text model")
```

```python
    if args.asr == "gemma":
        sup.asr = None
    elif args.asr:
        sup.asr = str(Path(args.asr).resolve())
```

- [ ] **Step 2: probe-languages.py**

After the imports add:

```python
import argparse
from cue.asr import MlxAsr
from cue.bootstrap import model_manifest_path
from cue.setupflow import hearing_model, hearing_model_path
ap=argparse.ArgumentParser(); ap.add_argument('--asr',help="hearing engine: unset = the manifest's; 'gemma' = Gemma's own hearing; or a model path"); args=ap.parse_args()
manifest=json.loads(model_manifest_path().read_text())
engine=None if args.asr=='gemma' else MlxAsr(Path(args.asr).resolve() if args.asr else hearing_model_path(models_root(),manifest)) if (args.asr or hearing_model(manifest)) else None
```

and change `backend=Backend(models_root())` to `backend=Backend(models_root(),asr=engine)`; change the output path to `out=root/('benchmarks/results/languages-gemma.json' if args.asr=='gemma' else 'benchmarks/results/languages.json')` and write `engine` into the JSON (`'hearing': args.asr or 'manifest'` next to `'load_s'`).

- [ ] **Step 3: Verify the flags parse**

Run: `.venv/bin/python scripts/eval-session.py --help | grep -c "hearing engine" && .venv/bin/python -c "import ast,sys; ast.parse(open('scripts/probe-languages.py').read()); print('ok')"`
Expected: `1` then `ok`

- [ ] **Step 4: Commit**

```bash
git add scripts/eval-session.py scripts/probe-languages.py
git commit -m "feat(eval): --asr gemma keeps Gemma's own hearing measurable; the manifest engine is the default"
```

---

### Task 7: The setup screen credits Whisper

**Files:**
- Modify: `plugin/sidebar.html:121`
- Modify: `plugin/src/strings.ts` (after `"sidebar.creditAligner"`)
- Modify: `plugin/src/runtime-install.ts` (`CREDIT_LINKS`)
- Test: `plugin/tests/install-runtime.test.ts:179-182`

- [ ] **Step 1: Write the failing test**: in `plugin/tests/install-runtime.test.ts` after the `gemma-e4b` assertion add

```ts
  assert.equal(openCreditLink('whisper', exec), true);
```

- [ ] **Step 2: Run it to see it fail**

Run: `npm test 2>&1 | tail -20`
Expected: the install-runtime test FAILS on `openCreditLink('whisper', exec)` returning `false`.

- [ ] **Step 3: Implement**

`plugin/src/runtime-install.ts`:

```ts
export const CREDIT_LINKS = {
  gemma: "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm",
  aligner: "https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-4bit",
  "gemma-e4b": "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm",
  whisper: "https://huggingface.co/mlx-community/whisper-large-v3-turbo",
} as const;
```

`plugin/src/strings.ts`, after the `sidebar.creditAligner` line:

```ts
  "sidebar.creditWhisper": "Whisper large-v3-turbo (OpenAI, MIT; MLX conversion by mlx-community)",
```

`plugin/sidebar.html` line 121 becomes:

```html
  <p id="setup-credits"><span data-i18n="sidebar.setupCreditsLead">Speech models:</span> <a href="#" data-link="gemma" data-i18n="sidebar.creditGemma">Gemma 4 E2B (Google, Apache 2.0)</a>, <a href="#" data-link="aligner" data-i18n="sidebar.creditAligner">Qwen3-ForcedAligner (Qwen team, Apache 2.0; MLX conversion by mlx-community)</a> <span data-i18n="sidebar.creditJoin">and</span> <a href="#" data-link="whisper" data-i18n="sidebar.creditWhisper">Whisper large-v3-turbo (OpenAI, MIT; MLX conversion by mlx-community)</a>.</p>
```

- [ ] **Step 4: Run the plugin tests and the build**

Run: `scripts/test > /tmp/gate.log 2>&1; tail -3 /tmp/gate.log; npm run build 2>&1 | tail -2`
Expected: all tests pass (the sidebar i18n test finds `sidebar.creditWhisper`); the build writes `dist/Cue.iinaplugin-0.1.0.iinaplgz`.

- [ ] **Step 5: Commit**

```bash
git add plugin/sidebar.html plugin/src/strings.ts plugin/src/runtime-install.ts plugin/tests/install-runtime.test.ts
git commit -m "feat(plugin): credit Whisper large-v3-turbo on the setup screen"
```

---

### Task 8: Licence notices for Whisper

**Files:**
- Create: `third_party/license-overrides/mit.txt`, `third_party/license-overrides/models/whisper-large-v3-turbo/SOURCE.txt`
- Modify: `scripts/collect_licenses.py` (`model_needles`, `copy_models`, `collect`), `THIRD_PARTY_NOTICES.md`
- Test: `helper/tests/test_collect_licenses.py`

- [ ] **Step 1: Write the failing test** (append to `helper/tests/test_collect_licenses.py`)

```python
def test_whisper_notice_ships_with_the_mit_text_and_both_pinned_revisions(tmp_path):
    prefix = make_prefix(tmp_path, [("Widget", "1.2.3", "widget license\n")])
    output = tmp_path / "licenses"
    result = run(prefix, output)
    assert result.returncode == 0, result.stderr
    assert "MIT License" in (output / "models" / "whisper-large-v3-turbo" / "LICENSE").read_text()
    source = (output / "models" / "whisper-large-v3-turbo" / "SOURCE.txt").read_text()
    assert "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb" in source and "41f01f3fe87f28c78e2fbf8b568835947dd65ed9" in source
    assert "Apache License" in (output / "models" / "gemma-4-e2b" / "LICENSE").read_text()
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest helper/tests/test_collect_licenses.py -q -k whisper`
Expected: FAIL with `FileNotFoundError` on `models/whisper-large-v3-turbo/LICENSE`

- [ ] **Step 3: Add the licence text and the source note**

`third_party/license-overrides/mit.txt`:

```
MIT License

Copyright (c) 2022 OpenAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

`third_party/license-overrides/models/whisper-large-v3-turbo/SOURCE.txt`:

```
Repository: mlx-community/whisper-large-v3-turbo
Revision: a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb
Processor files: openai/whisper-large-v3-turbo at revision 41f01f3fe87f28c78e2fbf8b568835947dd65ed9
Model card license field: mit (declared by openai/whisper-large-v3-turbo; the MLX conversion's card carries no license field)
Gated: no
Neither revision's file list has a LICENSE file.
The conversion's README says the weights were converted from openai/whisper-large-v3-turbo.
The LICENSE file beside this note is the MIT License, which that field names.
This note is not legal advice.
```

- [ ] **Step 4: Teach the collector about a MIT model**

In `scripts/collect_licenses.py`, `model_needles` gains the Whisper entry:

```python
    try:
        gemma = assets["gemma"]["revision"]
        gemma_e4b = assets["gemma-e4b"]["revision"]
        aligner = assets["aligner"]["revision"]
        whisper = assets["whisper-turbo"]["revision"]
    except KeyError as error:
        fail(f"models/manifest.json is missing {error}")
    return {
        "gemma-4-e2b": gemma,
        "gemma-4-e4b": gemma_e4b,
        "qwen3-forced-aligner-0.6b": "Qwen/Qwen3-ForcedAligner-0.6B",
        "qwen3-forced-aligner-0.6b-4bit": aligner,
        "whisper-large-v3-turbo": whisper,
    }
```

`copy_models` picks the licence the source note names:

```python
def copy_models(project: Path, output: Path, apache: Path, mit: Path) -> None:
    root = project / "third_party" / "license-overrides" / "models"
    for name, needle in model_needles(project).items():
        source = root / name / "SOURCE.txt"
        require_text(source, needle)
        licence = mit if "license field: mit" in source.read_text() else apache
        if licence is apache:
            require_text(source, "apache-2.0")
        destination = output / "models" / name
        destination.mkdir(parents=True)
        copy_bytes(source, destination / "SOURCE.txt")
        copy_bytes(licence, destination / "LICENSE")
```

In `collect`, after `require_text(apache, "Apache License")` add `mit = overrides / "mit.txt"` and `require_text(mit, "MIT License")`, and change the call at line 266 to `copy_models(project, output, apache, mit)`.

- [ ] **Step 5: The notices**

In `THIRD_PARTY_NOTICES.md`, insert before `## Silero VAD`:

```
Whisper large-v3-turbo is `openai/whisper-large-v3-turbo`, whose model card at revision `41f01f3fe87f28c78e2fbf8b568835947dd65ed9` declares `license: mit`. Cue hears with the pinned MLX conversion `mlx-community/whisper-large-v3-turbo` at revision `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb` and takes the tokenizer and feature-extractor files from the openai revision; both are required assets in `models/manifest.json`. Neither repository is gated and neither revision contains a LICENSE file. `licenses/models/whisper-large-v3-turbo/LICENSE` is the MIT License text that field names, with `SOURCE.txt` beside it.

```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest helper/tests/test_collect_licenses.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add third_party/license-overrides/mit.txt third_party/license-overrides/models/whisper-large-v3-turbo/SOURCE.txt scripts/collect_licenses.py THIRD_PARTY_NOTICES.md helper/tests/test_collect_licenses.py
git commit -m "docs(licenses): Whisper large-v3-turbo notice, MIT text and source note"
```

---

### Task 9: Documentation says Cue hears with Whisper

**Files:**
- Modify: `docs/install-cue.md:5,30`, `docs/install.md:21`, `README.md:5,73`, `docs/troubleshooting.md:5`
- Test: `helper/tests/test_install_guide.py:21`

- [ ] **Step 1: Update the guide test first**

In `helper/tests/test_install_guide.py` replace `assert "3.8 GB" in GUIDE` with

```python
    assert "5.5 GB" in GUIDE
    assert "Whisper" in GUIDE
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest helper/tests/test_install_guide.py -q`
Expected: FAIL on `"5.5 GB" in GUIDE`

- [ ] **Step 3: Edit the documents** (exact replacements)

`docs/install-cue.md` line 5: `about 8 GB of free disk space` → `about 10 GB of free disk space`; `about 3.8 GB` → `about 5.5 GB`.

`docs/install-cue.md` line 30: replace `Cue listens with Gemma 4 E2B. Under Advanced in the Cue sidebar, Speech model also offers Gemma 4 E4B, a larger model. It hears difficult dialogue more accurately, and it is a little slower.` with `Cue hears with Whisper large-v3-turbo and translates with Gemma 4 E2B. Under Advanced in the Cue sidebar, Speech model also offers Gemma 4 E4B, a larger translation model. It translates idioms and long sentences better, and it is a little slower.`

`docs/install.md` line 21: `Download 3,564,002,544 bytes` → `Download 5,182,597,375 bytes`; `allow 7 GB` → `allow 9 GB`.

`README.md` line 5: `A larger speech model, Gemma 4 E4B, is an optional download` → `A larger translation model, Gemma 4 E4B, is an optional download`; if the sentence before it says how Cue hears, say Whisper large-v3-turbo hears and Gemma translates.

`README.md` line 73: `- 模型資產共約 3.56 GB；另有編譯快取。` → `- 模型資產共約 5.18 GB（Gemma 4 E2B、Qwen3 對齊器、Whisper large-v3-turbo 聽寫模型）；另有編譯快取。`

`docs/troubleshooting.md` line 5: `- **MODEL_LOAD_FAILED**: no CPU/Whisper/cloud fallback is used.` → `- **MODEL_LOAD_FAILED**: Gemma, the Qwen aligner or the Whisper hearing model did not load; no CPU or cloud fallback is used.`

- [ ] **Step 4: Run the gate**

Run: `scripts/test > /tmp/gate.log 2>&1; tail -2 /tmp/gate.log`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add docs/install-cue.md docs/install.md README.md docs/troubleshooting.md helper/tests/test_install_guide.py
git commit -m "docs: Cue hears with Whisper large-v3-turbo; first-run download 5.5 GB"
```

---

### Task 10: Real evidence, acceptance row and memory

**Files:**
- Modify: `docs/acceptance.md`
- Modify (memory): `~/.claude/projects/-Users-calvinku-FunProjects-iina-cue/memory/translation-quality-testbed.md`

- [ ] **Step 1: The setup path an existing install takes** — move the checkout's Whisper folder aside and drive the helper's own setup API (the code the plugin calls):

```bash
cd /Users/calvinku/FunProjects/iina-cue && mv .runtime/models/whisper-large-v3-turbo .runtime/models/whisper-large-v3-turbo.bak && CUE_INSTALLED=0 .venv/bin/python - <<'EOF'
import json, time
from pathlib import Path
from cue.bootstrap import model_manifest_path
from cue.setupflow import Setup
root = Path(".runtime").resolve()
setup = Setup(root / "models", model_manifest_path())
before = setup.status(); print("needed GB", round(before["bytes_needed"] / 1e9, 2), "files_ready", before["files_ready"])
setup.action({"action": "download"})
while True:
    s = setup.status(); p = s["progress"]
    if p["phase"] not in {"downloading", "verifying"}: break
    time.sleep(5)
print("phase", p["phase"], "error", p["error"], "files_ready", s["files_ready"])
EOF
```

Expected: `needed GB 1.62`, `files_ready False`, then `phase idle error None files_ready True` (only the two Whisper assets fetched). Then `rm -r .runtime/models/whisper-large-v3-turbo.bak`. If the download fails, restore the folder with `mv` instead and record the failure.

- [ ] **Step 2: Product-path captions on the user-named film** (manifest engine, no flag):

```bash
CUE_HOME="$PWD/.runtime" scripts/cue-helper cache clear --media "/Volumes/WD18T/PlexLibrary/Movies/A Beautiful Mind (2001).mp4" | tail -1
CUE_INSTALLED=0 .venv/bin/python scripts/eval-session.py --media "/Volumes/WD18T/PlexLibrary/Movies/A Beautiful Mind (2001).mp4" --from-ms 115000 --to-ms 300000 --target zh-TW --source en | tail -1
CUE_HOME="$PWD/.runtime" scripts/dump-captions --media "/Volumes/WD18T/PlexLibrary/Movies/A Beautiful Mind (2001).mp4" --target zh-TW --from-ms 115000 --to-ms 300000 | head -12
```

Expected: the summary's `asr` is the checkout's `whisper-large-v3-turbo` folder with no flag given; the dump's first lines carry Whisper's transcript (e.g. “Thank you. It's not enough Hansen won the Carnegie scholarship.”). Then, in IINA (which runs the dev helper), enable Cue on the same film and confirm captions render; ask the user to confirm if it cannot be observed here.

- [ ] **Step 3: Language fixtures with both engines**

```bash
CUE_INSTALLED=0 .venv/bin/python scripts/probe-languages.py --asr gemma && CUE_INSTALLED=0 .venv/bin/python scripts/probe-languages.py
.venv/bin/python - <<'EOF'
import json
for name in ("languages-gemma", "languages"):
    r = json.load(open(f"benchmarks/results/{name}.json"))
    for row in r["samples"]: print(name, row["language"], row["status"], (row.get("auto_lid") or {}).get("code"), repr(row.get("transcript", ""))[:80])
EOF
```

Expected: every fixture `pass_pipeline_only` with both engines, the auto LID code equal to the fixture language, and Whisper's transcripts at least as close to the fixture scripts as Gemma's (record any zh Simplified/Traditional difference).

- [ ] **Step 4: Acceptance row and memory**

Add a row to `docs/acceptance.md` before the `VAD/music/quiet speech quality` row: status `pass local pipeline and setup API`, evidence: the setup step's numbers (bytes needed, phase, files_ready), the product-path run's summary (windows, failed, asr_s, rtf, `asr` value), the fixture results per language for both engines, the IINA observation (or that it awaits the user's confirmation), commits. Update the memory file's Whisper paragraph: it is now the product's hearing engine (required asset), the `--asr gemma` baseline flag, and that Gemma hearing is evaluation-only.

- [ ] **Step 5: Gate and commit**

```bash
scripts/test > /tmp/gate.log 2>&1; tail -2 /tmp/gate.log; npm run build 2>&1 | tail -1
git add docs/acceptance.md
git commit -m "docs(acceptance): Whisper as the hearing engine through the setup API, the product path and the language fixtures"
```
