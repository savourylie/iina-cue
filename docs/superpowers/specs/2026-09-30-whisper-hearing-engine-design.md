# Whisper as Cue's hearing engine — design

Date: 2026-09-30. Decision taken with the user after the evaluations recorded in `docs/acceptance.md` (rows “Dedicated speech-to-text model in front of Gemma” and “Dedicated hearing engine (Whisper) on a second English film …”).

## Goal

Cue hears with Whisper large-v3-turbo and translates with Gemma. Whisper is a required first-run asset like Gemma and the aligner: no new setting, no new UI. Gemma's own hearing stays in the code only for evaluation baselines and for a checkout without the asset.

## Why

Across four films and two judges Whisper never lost to Gemma's hearing: the external judge's misheard share fell from 16–26% to 5–8% on English (A Beautiful Mind, Pulp Fiction) with either translator, held level on Shoplifters (18% both, two runs) and fell from 23% to 8% on Tony Takitani. The user rejected a per-language or per-model toggle as confusing UI; one engine for every language removes the choice. Bundling was chosen over an Advanced download so that everyone gets the gain and the sidebar stays as it is.

## Not in scope

- Whisper's Japanese output carries less punctuation, so sentence units come out shorter. Separate work.
- The aligner collapsing on partial speech at a window's start (2–3 failed windows per stretch with every engine). Separate ticket.
- Chinese, Korean and the other source languages have only fixture-level checks with Whisper (see Evidence); no film-level judgement.

## Manifest (`models/manifest.json`)

Two new required assets, both into the folder `whisper-large-v3-turbo`:

| asset | repository | revision | files (bytes; check) |
|---|---|---|---|
| `whisper-turbo` | `mlx-community/whisper-large-v3-turbo` | `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb` | `config.json` (268; blob `6ac9a52a28f70a2e5681c250a470eca6e9c8cc3e`), `weights.safetensors` (1613977612; sha256 `951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6`, blob `26b12d9fb292a7bee72610f6e7e2ec84225feab7`) |
| `whisper-turbo-processor` | `openai/whisper-large-v3-turbo` | `41f01f3fe87f28c78e2fbf8b568835947dd65ed9` | `preprocessor_config.json` (340; `931c77a740890c46365c7ae0c9d350ba3cca908f`), `tokenizer.json` (2710337; `17456db595adc78a973f97d69d8cb50bc87c0b1c`), `tokenizer_config.json` (282843; `06ffdc8308eae6bb7bd1fdd81e94b0a881a539ab`), `special_tokens_map.json` (2186; `312bc106291bb51bf2cc1648df070bef963a0639`), `added_tokens.json` (34648; `1b33526d33aaa60d79f78ae8651dae50b730185a`), `normalizer.json` (52666; `dd6ae819ad738ac1a546e9f9282ef325c33b9ea0`), `vocab.json` (1036558; `0f3456460629e21d559c6daa23ab6ce3644e8271`), `merges.txt` (493869; `6038932a2a1f09a66991b1c2adae0d14066fa29e`), `generation_config.json` (3772; `cbe752958dc3e4671b0e0220aa1c545423a6d5f5`) |

The processor asset deliberately omits openai's `config.json`, which would overwrite the MLX one. `generation_config.json` is included because mlx_audio's loader reads alignment heads from it when present.

A new top-level field names the engine:

```json
"hearing_model": {"id": "whisper-turbo", "assets": ["whisper-turbo", "whisper-turbo-processor"], "folder": "whisper-large-v3-turbo"}
```

The download, verification, resume, cancel and disk checks are the existing ones; nothing in `setupflow.Setup` changes. First-run download grows from 3.6 GB to 5.2 GB; the consent screen computes it from the manifest. `manifest_hash` (a digest of `assets`) is part of the source cache key, so every existing cache is re-made after the update — the existing rule for pinned first-run models.

## Helper

- `setupflow.py`: `hearing_model(manifest) -> dict | None`, `hearing_model_path(models, manifest) -> Path` (`models/<folder>`), `hearing_model_complete(models, manifest) -> bool` (every file of both assets present, not a symlink, at its pinned size — the same cheap start-up check as `speech_model_complete`).
- `service.py`: `Supervisor.asr` is set at construction to `str(hearing_model_path(...))` when the manifest names a hearing model, else `None`. `asr_key()` returns `asr:<id>@<revision of the weights asset>` for the manifest engine and keeps `asr:<folder name>` for a path given by the evaluation driver. `start_worker`, `try_speech_model` and the worker are unchanged.
- `asr.py`: `MlxAsr.load()` raises `SETUP_REQUIRED` when `config.json` is missing under its path (as `Backend.load` does for Gemma), `MODEL_LOAD_FAILED` for any other load error. Never a silent fall-back to Gemma hearing. An empty transcript is `ASR_FAILED`, which leaves a hole and continues (existing rule).
- Source language: `auto` lets Whisper detect (`language=None`) and the text LID still runs afterwards; a chosen language is passed as its ISO code. The prompt is the previous window's text; no prompt before anything was heard (already on main).
- `doctor.py`: `model_assets` reports `whisper-turbo` (weights and tokenizer present) next to `gemma` and `aligner`.
- `scripts/eval-session.py`: `--asr` unset → manifest engine (product behaviour); `--asr gemma` → `sup.asr = None` (Gemma-hearing baseline); `--asr <path>` → override as today.

## Plugin

No new control. The setup screen's credit line is hand-written in `plugin/sidebar.html` with link ids resolved in `main.ts` (`openCreditLink`), so it gains one entry: “Whisper large-v3-turbo (OpenAI, MIT; MLX conversion by mlx-community)” with links to both repositories, plus its string in `strings.ts`. The memory floor stays 16 GB (`min_ram_bytes` unchanged).

## Documentation and licences

- README and `docs/install-cue.md`: Cue hears with Whisper large-v3-turbo and translates with Gemma 4 E2B; first-run download 5.2 GB; measured peak memory 3.1 GB (E2B) and 4.4 GB (E4B) without Metal; the E4B paragraph says it translates better (its hearing no longer matters).
- `docs/troubleshooting.md`: `MODEL_LOAD_FAILED` can now be the hearing model.
- `THIRD_PARTY_NOTICES.md`: Whisper large-v3-turbo paragraph (MIT; both repositories and revisions); `scripts/collect_licenses.py` maps the model; the MIT licence text lands under `models/` like the others.

## Tests (written first)

- manifest: `hearing_model` names two required assets that exist; every file has `bytes` and a `sha256` or `git_blob`; both assets share the folder; the manifest still validates for the existing tests.
- setupflow: the three helpers, including `hearing_model_complete` false on a missing or short file and on a symlink.
- service: a manifest with `hearing_model` gives `Supervisor.asr` the folder path and `asr_key()` the `id@revision` form; without it `asr` is `None`; the evaluation override keeps the folder-name key.
- asr: `SETUP_REQUIRED` on a missing `config.json`; `MODEL_LOAD_FAILED` otherwise.
- doctor: reports the Whisper asset.
- Full `scripts/test` and `npm run build` stay green.

## Evidence before calling it done

1. Move `.runtime/models/whisper-large-v3-turbo` aside and run the real setup flow from the checkout: only the 1.6 GB is fetched, verification passes, the smoke passes. This is also the path an existing install takes.
2. IINA on the user-named film with the dev helper: captions render; `dump-captions` shows the Whisper transcript.
3. `scripts/probe-languages.py` (or its equivalent) with the manifest engine on the en/zh/ja/ko fixtures: no regression against the Gemma-hearing results in `languages.json`.
4. A row in `docs/acceptance.md` and the memory note.

## Risks

- Whisper's Chinese output may be Simplified; the zh→zh-TW path is exercised by the fixture check, not by a film.
- Peak memory rises by about 1 GB; the documented floor stays 16 GB.
- Failed windows vary 0–3 per stretch between identical runs with every engine; this change does not alter that.
