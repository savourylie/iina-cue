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
