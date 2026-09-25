# [TICKET-017] One failed window never stops captions; translation output is constrained

## Status
`done`

## Dependencies
- Requires: None

## Description
On a Japanese film with casual, overlapping dialogue (Shoplifters, provided by the user), Cue stopped with "Translation failed" and, in the helper, with repeated alignment failures. Evidence from 2026-09-25:
- Gemma put a translation into two string literals in one `"text"` field, so the JSON did not parse.
- Decoding is deterministic: the same prompt sent twice gave identical output 12 times out of 12. The retry sends the same prompt, so it always fails the same way.
- The supervisor treats `TRANSLATION_FAILED`, and a second `ALIGNMENT_FAILED` or `ASR_FAILED`, as a session error. After that it schedules nothing, so captions stop for the rest of the video.
- Of 39 real batches, 1 (3%) was broken JSON. 8 (21%) were valid JSON but left hiragana or katakana in the Traditional Chinese output. They passed, because the script check only asks for Han characters, and Japanese kanji are Han.
- LiteRT-LM 0.17.1 has llguidance constrained decoding (`ConstrainedDecodingConfig` with `LL_GUIDANCE`, and `ResponseFormat.json`). With a JSON Schema that fixes the ids and requires non-empty text, 0 of 39 batches broke. It took 3.39 s per batch instead of 1.56 s. A schema pattern that forbids kana cleaned 8 of 8 leaking batches, and one output came back with a Latin transliteration.
- 35 of 60 windows with speech in the first 20 minutes failed alignment. With the source fixed to Japanese, 15 of 36 did. Each such window currently risks ending the session.

## Acceptance Criteria
- [x] Translation uses JSON Schema constrained decoding: exactly one object per cue, ids in order, and non-empty text. A broken JSON output can no longer occur.
- [x] For Traditional and Simplified Chinese and for Korean targets, a translation that contains hiragana or katakana is rejected. The check is in validation, not only in the prompt.
- [x] A retry changes something that matters. For example, it translates the failing cues one at a time. It never resends the identical prompt.
- [x] A window that still fails after its bounded retries becomes a failed hole. It is not `verified_no_speech`, the session stays usable, and the next window is scheduled. This holds for `ALIGNMENT_FAILED`, `ASR_FAILED` and `TRANSLATION_FAILED`.
- [x] The sidebar says that some captions could not be made and offers Retry. Retry prepares the failed holes again.
- [x] "Pause until captions are ready" does not hold playback forever at a hole that no longer has work scheduled.
- [x] On the Shoplifters range used for the evidence above, a helper session continues past every failure to the end of the range, and no failure ends the session.

## References
- `helper/src/cue/backend.py`: `send`, `translate`, `TARGET_SCRIPTS`.
- `helper/src/cue/core.py`: `translation_parse`.
- `helper/src/cue/service.py`: `tick`, the handling of failed jobs, `retry_window`, `skipped_language`, and `snapshot` `ready`.
- `plugin/src/control.ts`: `partialFailureStatus`, `preparationStatus`, `errorStatus`.
- `IINA_AI_SUBTITLES_SPEC.md` §7.1: a failed range must not be disguised as no speech, and failed ranges do not join coverage.
- `docs/tickets/015-silero-vad-no-speech.md`: the Shoplifters measurements.

## Implementation Notes
- Required constraints: never invent or distribute times (AGENTS.md). A failed hole has no cues. Never resume a user pause, and never reclaim a manually changed subtitle selection.
- Built on the TICKET-015 branch. Both change `service.py`; this ticket does not need the VAD itself.
- Suggested approach: pass `constrained_decoding_config` when creating the conversation and `response_format` when sending. The schema uses `prefixItems` with `const` ids and a `minLength` text. For the target-script rule, validation is the gate; a kana-free pattern can be tried on the retry.
- Out of scope: translation context from earlier cues (spec §7), locking the detected language, and larger models (TICKET-018).

## As-Built Notes

### 2026-09-25
- Translation passes a JSON Schema to LiteRT-LM's llguidance constrained decoding: `prefixItems` with a `const` id per cue, `minItems` and `maxItems` equal to the cue count, `items: false`, and text of 1–1000 characters. ASR calls are unchanged. The batch that failed with two strings in one field now translates on the first call, in 3.7 s.
- `check_target_script` keeps the Han and Hangul rule, and it now rejects hiragana or katakana for zh-TW, zh-CN and ko. It still passes kana for ja.
- If the batch fails, each cue is translated alone with the kana-free pattern (`^[^\u3040-\u30ff]+$`) for those targets. The script rule then applies to the joined batch, so a name-only cue can stay in Latin letters. The retry never resends the first prompt.
- The supervisor keeps the half-window retry for alignment and ASR. After that, and at once for `TRANSLATION_FAILED`, the window becomes a failed hole: `failed_ranges` plus `failure`, which holds code, detail and range. Scheduling skips holes. Other codes, such as a missing model, a changed file or a crashed worker, still end the session. Retry clears failed holes and ranges skipped for language.
- `ready` treats failed and skipped holes as settled, so pause-until-ready does not wait for them. `buffer_*` still counts only installed captions. With the playhead in a failed hole, the sidebar shows "No captions for this part" with Retry. In a range skipped for language it shows "Language unclear". Review found that the settled `ready` would otherwise have replaced that message with "Captions ready".
- Real sessions on Shoplifters 0–798 s: the supervisor, the worker and the real models, with the viewer never ahead of settled ranges. Before (the TICKET-015 code): the session ended at 138 s with `ALIGNMENT_FAILED` and 0 captions, for both `auto` and `ja`. After: both reached 798 s with no session error. `auto`: 131 captions, 11 holes (136 s), 1 range skipped for language (8 s). `ja`: 134 captions, 13 holes (152 s). 96 and 97 of the 133 embedded English lines had a Cue caption overlapping them in time. No caption contained kana.
- Most holes are 8 s: the half that failed again after the half-window retry. Accuracy is still limited by E2B transcription. For example, "A crusher... is shaped like a hammer" came out as "是碎石。 / 這樣的黏土就形狀了。". TICKET-018 covers larger models.
- Not run inside IINA. The plugin changes are covered by unit tests only.

### 2026-09-25 (release)
- Shipped in runtime 0.1.8, together with TICKET-015. 283,956,592 bytes, SHA-256 `90d9c4f0f20200b26ab15921e0de57b070febf7dcb59fb4a12bd117cb52d8822`, notarization `4b4e80e6-948b-46e5-b5b1-0d4310783334`, Accepted with no issues, minimum macOS 14.0. Hosted on Hugging Face `onionmonster/cue-runtime` at commit `35ab9c22ad9890a0598c13d70247919e8754633b`, with GitHub Release `runtime-0.1.8` as backup. The plugin pins both. Runtime 0.1.7 was notarized but never published.
- Checks on the signed archive: the plugin's unpack script installs it and deletes the archive, Gatekeeper accepts `libonnxruntime` as a Notarized Developer ID, and the setup smoke test passes. The plugin's install function downloaded it from Hugging Face and unpacked version 0.1.8 in 95.5 s.
- Existing installs keep their old runtime until TICKET-016.

## Testing
- Unit tests: the schema sent for a batch; kana rejected for zh and ko targets and accepted for ja; the retry prompt differs from the first; the supervisor turns failures into holes and schedules the next window; Retry clears the holes; `ready` with a hole ahead.
- Real inference: the same Shoplifters range through a helper session. Record session state, holes and coverage against the embedded English subtitles, before and after.
- `scripts/test` and `npm run build`.
