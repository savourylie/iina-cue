# [TICKET-015] Detect stretches without speech with Silero VAD

## Status
`done`

## Dependencies
- Requires: #001 ✅, #004 ✅, #007 ✅

## Description
A film's opening credits, a music cue, or a quiet scene makes Cue report a problem, and a fixed source language stops Cue for the rest of the video.

Root cause, reproduced on 2026-09-25 with generated audio (40 s of pink noise and a soft chord, then speech):
- The pipeline recognises only exact digital silence as "no speech" (`helper/src/cue/pipeline.py`). Music and ambient sound always go to ASR.
- On such audio, Gemma still writes a few characters: `"A."` with source `auto`, `"I'm"` with source `en`.
- With source `auto`, text language identification fails (`LANGUAGE_UNCERTAIN`). The supervisor skips the range and shows "Language unclear. Earlier audio had no clear language. Press play to check later audio, or choose a source language and retry." The user saw this on a film opening. Captions resumed when speech began.
- With a fixed source, the aligner cannot place the invented text, so `ALIGNMENT_FAILED` occurs. The half-window retry fails too. The supervisor marks the session `error` and schedules nothing more. Reproduced result: error at 4.3 s, 0 captions, although speech starts at 40 s.

The specification plans Silero VAD for this: the VAD row in §3.2, `verified_no_speech` in §7.1, and §15.3 "a 60 s opening of pure music or silence does not block viewing". The quality targets in §14.4 say non-speech must not produce invented dialogue. This ticket adds the VAD so a window without speech never reaches ASR and becomes verified non-speech coverage.

## Acceptance Criteria
- [x] A window in which Silero VAD finds no speech skips ASR, language identification, alignment and translation. Its range is committed as `verified_no_speech` with no cues, and playback coverage continues past it.
- [x] With the reproduction clip (40 s of ambient sound, then speech), both source `auto` and source `en` produce captions for the speech. Neither run reports `LANGUAGE_UNCERTAIN`, a skipped range, or a session error for the ambient part.
- [x] Speech is not filtered out. The spoken fixtures, speech under music, and quiet speech keep their captions. The decision thresholds and the measured probabilities that justify them are recorded in this ticket.
- [x] VAD only decides whether a window contains speech. Cue start and end times still come from forced alignment.
- [x] The VAD model loads once in the persistent inference worker, not once per window. It runs on the CPU.
- [x] The model is the official `silero_vad.onnx` from the PyPI `silero-vad` 6.2.3 wheel, verified by SHA-256 before use. It runs with `onnxruntime`, and neither PyTorch nor the `silero-vad` package is installed.
- [x] The cache key includes the VAD model and rule, so results cached before this change are not reused.
- [x] Runtime 0.1.7 includes onnxruntime and the model. It still targets macOS 14.0, is notarized, and its license notices cover Silero VAD (MIT) and onnxruntime with its dependencies. Publishing it and pointing the plugin at it wait for the user's approval at the time.

## References
- `IINA_AI_SUBTITLES_SPEC.md`: §3.2 VAD row, §6.1 "VAD only decides whether there is speech; it is not a forced aligner", §7.1 coverage kinds, §14.4 non-speech and quiet-speech targets, §15.3 music opening.
- `helper/src/cue/pipeline.py`: digital-silence bypass and `coverage_kind`.
- `helper/src/cue/service.py`: `LANGUAGE_UNCERTAIN` skip, `ALIGNMENT_FAILED` retry, and the terminal `error` state; `source_profile` digest.
- `helper/src/cue/backend.py`: `send` treats empty output as `ASR_FAILED`; `language` needs 12 letters.
- `plugin/src/control.ts`: `preparationStatus` shows "Language unclear" for skipped ranges.
- `scripts/build-runtime`, `scripts/collect_licenses.py`, `THIRD_PARTY_NOTICES.md`: runtime contents and notices.
- `helper/tests/test_pipeline.py`: fake-backend pattern for pipeline tests.

## Implementation Notes
- Required constraints: one persistent inference subprocess (AGENTS.md). No model download at inference time. No global Python changes. Local media only; test audio is generated with `say` and FFmpeg.
- Required constraints: `onnxruntime` 1.30.0 is MIT and has a `macosx_14_0_arm64` wheel for Python 3.12. The `silero-vad` package requires PyTorch, so only its model file and MIT license are used. Wheel SHA-256 `7b7f5436cfcb02fae583a05b512ea96467fd449fe54cb49a5e4f06c51a1e43b8`.
- Suggested approach: follow the official `OnnxWrapper` exactly: 512-sample frames at 16 kHz, 64 samples of context from the previous frame, state carried between frames, and the last frame zero-padded. Decide speech with the segment rule of `get_speech_timestamps_from_probs`. Check the streaming implementation against the wheel's torch-free `silero_vad_16k_sequence.onnx`, which its authors describe as bit-exact.
- Out of scope: a window that has speech but still fails alignment twice still ends the session with a fixed source language. That is a separate change.
- Runtime updates for existing installs are TICKET-016.

## As-Built Notes

### 2026-09-25
- `helper/src/cue/vad.py` runs the official `silero_vad.onnx` through onnxruntime 1.30.0 on one CPU thread. It follows the wheel's `OnnxWrapper`: 512-sample frames, 64 samples of context, state carried across frames, and the last frame zero-padded. Against the wheel's torch-free `silero_vad_16k_sequence.onnx` on six generated clips, every frame probability matched exactly (maximum difference 0.0).
- A window has speech when the segment rule of `get_speech_timestamps_from_probs` finds a segment. It uses Silero's defaults: threshold 0.5, exit 0.35, minimum speech 250 ms, and minimum silence 100 ms. The reduced rule matched the official function on all six clips and on 3,000 random probability sequences, with 0 differences, when padding is 0. Maximum-duration splitting and padding move edges but never decide whether a segment exists.
- Measured peak probabilities on generated audio: spoken English 1.000, the same under pink noise and a chord 1.000, the same at −24 dB 1.000, pink noise with a chord 0.026, white noise 0.034. The defaults were kept.
- The pipeline runs VAD after the digital-silence check and before ASR. It skips VAD when a cached transcript already exists. A window without speech returns `verified_no_speech` with language `und` and method `voice_activity`. VAD takes about 61 ms for an 18 s window.
- The model loads once per inference worker. A missing or altered model raises `SETUP_REQUIRED`. `doctor` reports whether the model matches.
- `VAD_ID` joins the source profile, so earlier cache entries are not reused.
- Found in review: the cache took the language of the last chunk, and now many chunks without speech carry `und`. That would have turned "English (original)" into "Original" during music. `Cache.read` now keeps the last known language, and `und` wins only when no chunk has a language.
- `scripts/fetch-vad` downloads the pinned wheel from PyPI and checks the wheel, the model, and the license against pinned SHA-256 values. `scripts/setup-dev` puts the model in `.runtime/vad`, and `scripts/build-runtime` puts it in the runtime's `vad/`. The license and the source record go to `licenses/models/silero-vad/`. flatbuffers 25.12.19, pulled in by onnxruntime, has no license file in its wheel, so it has an exact-version Apache-2.0 override.
- Runtime 0.1.7: 287,101,140 bytes compressed, and every Mach-O file targets macOS 14.0 or older, including `libonnxruntime`. Notarization `cd15e586-8e8f-42a0-b9cf-121883f07bff` was Accepted with no issues. It is not published, and the plugin still points at 0.1.6.
- Real inference, generated clip of 40 s ambient sound then speech. Before: source `en` ended in a session error at 4.3 s with 0 cues, and `auto` skipped 0–20 s with "Language unclear". After: both covered the whole clip with no skipped range and no error, with cues only at 39.96–49.28 s. A clip of speech, 60 s ambient, then speech got cues at 0–6.9 s and 67.1–74.0 s in both modes. Speech under noise and speech at −24 dB kept all 3 cues. Runtime 0.1.7 itself, in installed mode, gave the same results, and its setup smoke test passed in 6.1 s.
- Real film, user-provided (Shoplifters, Japanese, 5.1), first 20 minutes, against its embedded English subtitles. 18 of 78 windows were judged without speech. Only three reference lines fell in them: a whispered "Hey." at 1:39, the on-screen title "Shoplifters", and "Ohh...". At the line level, 38 of 194 lines never reach 0.5 within their own time. They are mostly muffled speech through a wall and whispering, and they sit in windows that still have other speech. The center channel alone did not raise those probabilities.
- The same film shows problems outside this ticket, recorded separately: 35 of 60 speech windows failed alignment, Gemma wrote Korean for Japanese speech, and translation JSON failed identically on both attempts.
- Not done: no run inside IINA, where the linked plugin still starts the installed 0.1.6. Publishing 0.1.7 and pointing the plugin at it wait for approval, and TICKET-016 covers updating existing installs.

## Testing
- Unit tests: the VAD on generated silence, noise and speech; the segment rule on crafted probability sequences; the pipeline with a stub VAD, where no speech means ASR is never called and speech means the normal path.
- Real inference: the session-level reproduction with source `auto` and `en`, plus speech under music and quiet speech. Record the results in this ticket.
- `scripts/test` and `npm run build`. Build runtime 0.1.7 and confirm that the build's macOS 14.0 check passes.
