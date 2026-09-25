# [TICKET-018] Optional larger models in Advanced

## Status
`pending`

## Dependencies
- Requires: #006 ✅, #009 ✅

## Description
Gemma 4 E2B is Cue's only model. On casual Japanese film dialogue it mishears less common words ("クラッシャー" heard as "グラシャ", "コロッケ" as "とろっけ"), and with source `auto` it sometimes writes Japanese speech in Korean letters. Forced alignment then cannot place the invented words, and the window is lost. The user wants two larger Gemma 4 models offered in Advanced, for users who choose to download them. E2B stays the default.

Both are public, Apache-2.0 and not gated, and both take audio:
- Gemma 4 E4B: `litert-community/gemma-4-E4B-it-litert-lm`, file `gemma-4-E4B-it.litertlm`, 3.66 GB, with a separate audio encoder of about 300M parameters.
- Gemma 4 12B Unified: `litert-community/gemma-4-12B-it-litert-lm`, file `gemma-4-12B-it.litertlm`, 6.88 GB. It takes audio without a separate encoder.

## Acceptance Criteria
- [ ] Advanced lists E2B (default), E4B and 12B with download size, disk space needed, memory needed, and whether each is downloaded.
- [ ] A model downloads only after the user chooses it. The download uses the existing pinned, resumable, verified path: a pinned revision and a SHA-256 per file. It passes the smoke test before it can be selected.
- [ ] Choosing a model restarts the inference worker with it. It is refused while a session or an MKV copy uses the worker, and it can be switched back to E2B.
- [ ] The model in use is part of the cache key, so captions from one model are never served as another's.
- [ ] A Mac without enough memory for a model cannot select it. The requirement is measured for each model, not guessed.
- [ ] A model can be removed to free disk space. E2B cannot be removed while it is the only installed model.
- [ ] LiteRT-LM 0.17.1 is confirmed to transcribe audio with each model before release. The 12B has no separate audio encoder, so that is checked first.
- [ ] E4B and 12B are measured against E2B on the same 13 minutes of Shoplifters: the share of windows with speech that succeed, reference coverage, speed per window, and peak memory.
- [ ] License notices cover the new model artifacts.
- [ ] `AGENTS.md` changes "no larger model substitution" to say that E2B stays the default and larger models are used only by explicit user choice. This needs the user's approval.

## References
- `models/manifest.json`, `helper/src/cue/setupflow.py`: pinned assets, resumable verified download, smoke test.
- `helper/src/cue/backend.py`: model loading and `send`.
- `helper/src/cue/service.py`: worker lifecycle and the source profile digest.
- `plugin/sidebar.html`, `plugin/src/setup-controller.ts`: the setup card and Advanced area.
- `IINA_AI_SUBTITLES_SPEC.md`: main model choice ("evaluate E2B first, do not default to 12B") and §16 (report the bottleneck and alternatives before changing the ASR model).

## Implementation Notes
- Required constraints: no model download without the user's consent. This includes the evaluation downloads during development (3.66 GB and 6.88 GB). Local inference only. One persistent inference subprocess.
- Required constraints: the default stays E2B, and nothing switches models on its own.
- Suggested approach: a model catalog next to `models/manifest.json`, one asset set per model that shares the aligner. A "model" field in the setup API. The worker reads the selected model when it starts.
- Risk: the 12B is about 6.9 GB before any working memory, so it probably needs 24–32 GB. Measure it first.

## Testing
- Unit tests: catalog pinning, consent before download, refusal while busy, cache key per model, memory gating.
- Real inference: transcription with each model on the generated fixtures and on the Shoplifters range. Record speed and peak memory.
- Manual: download, select, use and remove a model in IINA.

## As-Built Notes

### 2026-09-25
- Catalog: `models/manifest.json` adds `optional_assets` (E4B and 12B, pinned by revision and SHA-256) and `speech_models` (id, asset, file, `min_ram_bytes`, `cache_bytes`), with `default_speech_model: "e2b"`. First-run setup still downloads only E2B and the aligner.
- Helper: `POST /v1/setup/actions` takes `model_download`, `model_cancel`, `model_use` and `model_remove` with a `model` id. `GET /v1/setup` adds `speech_models`: per model the download size, disk space needed, state, memory needed, whether this Mac has it, and the selection, plus download and trial progress. Downloads reuse the pinned, resumable, SHA-256-checked fetch. A verified file is remembered in `models/.verified.json` by size, mtime and expected hash, so status polls do not hash gigabytes again.
- Switching: `model_use` restarts the one persistent worker with the chosen file and runs the setup's spoken test clip. Cue keeps the model only if the clip passes and records it in `models/.speech-model.json`; otherwise it restarts with the previous model. A trial is refused with `SETUP_BUSY` while a session, a caption job, a smoke job or an MKV copy uses the worker, and new sessions are refused with `MODEL_SWITCHING` until the trial ends, so no session is keyed to a model that did not make its captions. At helper start, a recorded model whose files are missing or not at their pinned size falls back to E2B.
- Cache key: the source profile includes `<model id>@<revision>`. The manifest's share of the key now hashes only the first-run `assets`, so catalog figures never invalidate cached captions. This changes every key once: captions cached by runtime 0.1.8 are prepared again after the update.
- Remove deletes the model file, a partial download, its verification marker and its LiteRT-LM compile cache in `models/compiled`. E2B is never removable in Advanced, because first-run setup and the fallback depend on it. That is stricter than the criterion, which only forbade removing it while it is the only installed model.
- Disk space needed is download plus compile cache, both measured here: E2B 2.59 + 0.90 GB, E4B 3.66 + 2.32 = 5.98 GB, 12B 6.88 + 5.99 = 12.87 GB. A download is refused with `DISK_FULL` below that.
- Memory needed is the smallest of 16, 24 and 32 GB that is at least twice what the worker uses: its peak physical footprint plus its GPU weight cache, which stays mapped while the model runs. E2B 4.9 + 0.7 = 5.6 GiB gives 16 GB (the existing requirement), E4B 5.5 + 2.0 = 7.5 GiB gives 16 GB, and 12B 5.6 + 5.5 = 11.1 GiB gives 24 GB. The peak resident set sampled every 15 s agrees but varies between runs (E2B 5.3 and 3.8 GiB). A Mac with less memory than required cannot download or choose the model.
- Sidebar: Advanced → Speech model has one radio per model with its name, description and facts (download size, disk space and memory, or "Downloaded"), then progress with Cancel, Resume, Remove, the trial result, and helper refusals as sentences. Only an installed model that fits this Mac can be chosen. Credits for E4B and 12B open their Hugging Face pages through the plugin. The preferences page credits name all three models. Its old `licenses/` link pointed into the plugin, which has no such folder, so it now names `~/Library/Application Support/Cue/runtime/licenses`.
- Licenses: `third_party/license-overrides/models/gemma-4-e4b` and `gemma-4-12b` record the repository, revision, the cards' `apache-2.0` field and the missing LICENSE file. `scripts/collect_licenses.py` copies both with the Apache-2.0 text, and `THIRD_PARTY_NOTICES.md` names both revisions.
- `AGENTS.md` allows a larger model only by explicit user choice, as the user approved (commit 610d9ea).
- Found while testing: the setup progress file and the new verification markers were read-modify-written through one fixed `.tmp` name. A download thread and a status request on another HTTP thread could collide, and the rename then failed the request. Both writes now share a lock and a per-writer temporary name; a 32-thread test failed before the fix and passes after it. The model tests also stub the macOS voice, whose clip took over the tests' old 3 s wait under load.

Measurements on an Apple M1 Ultra with 64 GB and macOS 27.2. Real helper sessions (`Supervisor`, the persistent worker, and a viewer that never runs ahead of settled coverage) on Shoplifters 0–798 s, source `auto`, target zh-TW, against the 133 embedded English lines. Each model was chosen through `model_use`, so its trial ran first; E4B and 12B wrote their compile caches during the trial. A second E2B run gave the same 166 captions, 118 lines and holes.

| | E2B | E4B | 12B |
|---|---|---|---|
| Trial on the spoken clip | 6.0 s | 14.6 s | 32.3 s |
| Time to prepare 798 s | 392 s | 403 s | 629 s |
| Reference lines with a caption | 118 (89%) | 119 (89%) | 83 (62%) |
| Failed holes | 5, 40 s | 5, 72 s | 10, 136 s |
| Skipped for language | 2, 32 s | none | 5, 64 s |
| Peak resident set of the worker, sampled every 15 s | 5.3 GiB (3.8 on a second run) | 7.3 GiB | 10.1 GiB |
| Peak physical footprint of the worker | 4.9 GiB (second run) | 5.5 GiB | 5.6 GiB |
| GPU weight cache | 0.7 GiB | 2.0 GiB | 5.5 GiB |

Per window, from the window-by-window evaluation of the same range before TICKET-019 (no half-window retry or kept prefix):

| | E2B | E4B | 12B |
|---|---|---|---|
| Windows with speech that succeeded, `auto` | 13/36 (36%) | 14/36 (39%) | 14/38 (37%) |
| Windows with speech that succeeded, `ja` | 21/36 (58%) | 18/38 (47%) | 16/36 (44%) |
| Median seconds per successful 16 s window, `auto` / `ja` | 5.5 / 5.4 | 6.5 / 5.7 | 7.9 / 7.5 |

- E4B hears hard words better. In the window-by-window evaluation with source `ja`, E2B wrote "とろっけ" twice and "グラシャ" once where E4B wrote "コロッケ"; with `auto`, E4B wrote no Hangul (E2B 4 lines, 12B 10). In the session, no E4B range was skipped for language. Coverage stays level because forced alignment, not transcription, limits it (TICKET-019).
- 12B is worse on this film. In `ja` it answered in English ("English: No, no, no…"), fell into Korean repetition loops, and spaced out Japanese tokens; 4 `auto` windows came back with no text. It stays in the catalog as this ticket requires, described as experimental. Whether to keep offering it is the user's decision.
- LiteRT-LM 0.17.1 transcribes audio with both. The 12B has no separate audio encoder; it writes a streaming audio encoder cache instead, passed its trial and finished the range.
- Not verified: download, choose, use and remove in IINA. The installed runtime 0.1.8 predates these helper changes, so that needs runtime 0.1.9 (TICKET-019 and this ticket) with the plugin pinned to it. Speed and memory on any other Mac are not measured; a Mac with less memory bandwidth will be slower, 12B most of all.
