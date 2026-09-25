# [TICKET-015] Detect stretches without speech with Silero VAD

## Status
`pending`

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
- [ ] A window in which Silero VAD finds no speech skips ASR, language identification, alignment and translation. Its range is committed as `verified_no_speech` with no cues, and playback coverage continues past it.
- [ ] With the reproduction clip (40 s of ambient sound, then speech), both source `auto` and source `en` produce captions for the speech. Neither run reports `LANGUAGE_UNCERTAIN`, a skipped range, or a session error for the ambient part.
- [ ] Speech is not filtered out. The spoken fixtures, speech under music, and quiet speech keep their captions. The decision thresholds and the measured probabilities that justify them are recorded in this ticket.
- [ ] VAD only decides whether a window contains speech. Cue start and end times still come from forced alignment.
- [ ] The VAD model loads once in the persistent inference worker, not once per window. It runs on the CPU.
- [ ] The model is the official `silero_vad.onnx` from the PyPI `silero-vad` 6.2.3 wheel, verified by SHA-256 before use. It runs with `onnxruntime`, and neither PyTorch nor the `silero-vad` package is installed.
- [ ] The cache key includes the VAD model and rule, so results cached before this change are not reused.
- [ ] Runtime 0.1.7 includes onnxruntime and the model. It still targets macOS 14.0, is notarized, and its license notices cover Silero VAD (MIT) and onnxruntime with its dependencies. Publishing it and pointing the plugin at it wait for the user's approval at the time.

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

## Testing
- Unit tests: the VAD on generated silence, noise and speech; the segment rule on crafted probability sequences; the pipeline with a stub VAD, where no speech means ASR is never called and speech means the normal path.
- Real inference: the session-level reproduction with source `auto` and `en`, plus speech under music and quiet speech. Record the results in this ticket.
- `scripts/test` and `npm run build`. Build runtime 0.1.7 and confirm that the build's macOS 14.0 check passes.
