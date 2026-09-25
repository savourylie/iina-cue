# [TICKET-017] One failed window never stops captions; translation output is constrained

## Status
`pending`

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
- [ ] Translation uses JSON Schema constrained decoding: exactly one object per cue, ids in order, and non-empty text. A broken JSON output can no longer occur.
- [ ] For Traditional and Simplified Chinese and for Korean targets, a translation that contains hiragana or katakana is rejected. The check is in validation, not only in the prompt.
- [ ] A retry changes something that matters. For example, it translates the failing cues one at a time. It never resends the identical prompt.
- [ ] A window that still fails after its bounded retries becomes a failed hole. It is not `verified_no_speech`, the session stays usable, and the next window is scheduled. This holds for `ALIGNMENT_FAILED`, `ASR_FAILED` and `TRANSLATION_FAILED`.
- [ ] The sidebar says that some captions could not be made and offers Retry. Retry prepares the failed holes again.
- [ ] "Pause until captions are ready" does not hold playback forever at a hole that no longer has work scheduled.
- [ ] On the Shoplifters range used for the evidence above, a helper session continues past every failure to the end of the range, and no failure ends the session.

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

## Testing
- Unit tests: the schema sent for a batch; kana rejected for zh and ko targets and accepted for ja; the retry prompt differs from the first; the supervisor turns failures into holes and schedules the next window; Retry clears the holes; `ready` with a hole ahead.
- Real inference: the same Shoplifters range through a helper session. Record session state, holes and coverage against the embedded English subtitles, before and after.
- `scripts/test` and `npm run build`.
