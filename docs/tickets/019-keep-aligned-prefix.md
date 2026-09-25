# [TICKET-019] Keep the aligned part of a window when alignment collapses

## Status
`done`

## Dependencies
- Requires: None

## Description
Forced alignment is now the largest cause of missing captions on dense, casual dialogue. On Shoplifters (Japanese, user-provided), 0–798 s, with E2B and source `ja`, 15 of 36 windows with speech failed with `ALIGNMENT_FAILED`. Larger models did not reduce this: E4B failed 20 windows and 12B failed 17.

The rule is all or nothing per window. `coalesce_quantized_units` accepts at most 3 consecutive zero-length tokens, spanning at most 1.5 s, and otherwise rejects the whole 16 s window. In the failed windows, the aligner usually placed most tokens plausibly:
- In 6 of the 15, at most 15% of the tokens were unplaceable, often a single token.
- At 378–394 s, 17 of 18 tokens have plausible times. Only the last particle 「な」 has zero length, and 「だけ」 before it is stretched to 2.16 s. The window is rejected ("collapsed trailing alignment"), and "I fell" and "Does it hurt?" are lost with it.
- In 3 of the 15, more than 40% of the tokens were unplaceable, mostly invented text over whispering or muffled speech. Rejecting those is correct.

This ticket keeps the aligned part of the window before the collapse. The next window starts at the collapse and transcribes and aligns the rest again, so no text is silently dropped and no time is invented.

## Acceptance Criteria
- [x] When coalescing finds a collapsed run, the aligned units before it are kept, with their measured times unchanged. A collapsed run is more than 3 zero-length tokens, or a span over 1.5 s. For a trailing collapse, the stretched unit before the run is not kept.
- [x] The kept units must spell out the beginning of the transcript: their normalized text is a prefix of it. Punctuation is restored on that prefix only.
- [x] The window commits up to the start of the collapse, and the next window starts there. The text after the collapse is transcribed and aligned again, not discarded.
- [x] If nothing would be kept, or the committed part is shorter than 2 s, the window fails as it does today: half-window retry, then a hole.
- [x] No cue time is invented or distributed. Every committed cue starts and ends on aligner times.
- [x] Real helper sessions on Shoplifters 0–798 s, `auto` and `ja`, cover more reference lines than TICKET-017, which covered 96 and 97 of 133 lines, with 11 holes over 136 s and 13 holes over 152 s. The hole time is reported too.

## References
- `helper/src/cue/core.py`: `coalesce_quantized_units`, `validate_units`, `restore_transcript`, `assemble`.
- `helper/src/cue/backend.py`: `align`.
- `helper/src/cue/pipeline.py`: `committed_end`, the trailing draft second, crossing units, and the "unresolved boundary made no progress" guard.
- `helper/tests/test_core.py`, `helper/tests/test_pipeline.py`: existing alignment and boundary tests.
- `docs/tickets/017-captions-survive-failed-windows.md`: the before measurements.

## Implementation Notes
- Required constraints: source times come from forced alignment only; never invent or distribute times (AGENTS.md). A kept prefix is still complete coverage for its committed range, so it must not contain a gap that hides unplaced speech. Committing ends at the collapse, and the rest is prepared again.
- Built on `main` after TICKET-017; it does not need the failure holes to work.
- Suggested approach: a coalescing variant that returns the prefix and the cut time, used by the pipeline. `validate_units` and `restore_transcript` gain a prefix mode. The existing `committed_end` path moves the next window.
- Out of scope: the 8-bit aligner, shorter windows for dense dialogue, and changing the collapse limits themselves.

## As-Built Notes

### 2026-09-25
- `coalesce_until_collapse` coalesces as before, and stops at the first run it cannot place: more than 3 zero-length tokens, or a span over 1.5 s. It returns the units before the run, the time where the run begins, and the reason. For a trailing run, it also returns the stretched word before it to the next window, so the cut is at that word's start. `coalesce_quantized_units` is now the all-or-nothing wrapper and keeps its messages.
- `Backend.align(..., partial=True)` returns `(units, cut)`, and the pipeline always uses it. `validate_units(prefix=True)` accepts only kept units whose normalized text begins the transcript. `restore_transcript(prefix=True)` maps punctuation onto that prefix and gives the last kept word its closing punctuation, never an opening bracket.
- `committed_end` becomes the earlier of the existing boundary (trailing draft second, known right chunk, or end) and `zero + cut`. `timings.alignment_cut_ms` records the cut. If less than 2 s would be committed (`MIN_KEPT_MS`), or nothing was kept, the window fails with `ALIGNMENT_FAILED` as before: half-window retry, then a hole.
- Cue times are still aligner times. The cut only bounds committed coverage. No word before the cut is unplaced, and the text after it is transcribed and aligned again by the next window.
- Real helper sessions, Shoplifters 0–798 s, E2B, target zh-TW, against the 133 embedded English lines:
  - `auto`: TICKET-017 captioned 96 lines (72%), with 11 holes over 136 s. This ticket captions 118 lines (89%), with 5 holes over 40 s and 2 ranges skipped for language over 32 s. Captions went from 131 to 166.
  - `ja`: 97 lines (73%) with 13 holes over 152 s became 115 lines (86%) with 7 holes over 56 s. Captions went from 134 to 165.
  - No caption contained kana. Committed chunks went from 46 to 64 (`ja`) and from 48 to 59 (`auto`), because a partial commit leaves the rest to a new window.
- Mutation checks: ignoring the cut fails 2 pipeline tests, and removing the 2 s minimum fails 1.
- Cost: an instrumented rerun of the `ja` session gave identical results: 165 captions, 115 of 133 lines, and the same 7 holes. It ran 85 jobs, which sent 1,242 s of audio for 798 s of film, 56% more than the film. That is the rest after each cut, the retries, and context. The jobs took 507 s in total, with a median of 4.3 s per window. That is about 1.6 times faster than playback on this M1 Ultra. Whole-session wall time varied between runs: 354 s for TICKET-017, and 766 s and 508 s for two runs of this ticket with identical output. The slowest job, 32.5 s at 316–332 s, took 7.7 s when run alone, so the outlier is not in the window itself. Whether a slower Mac keeps up is not measured yet. It belongs with the memory and speed measurements for TICKET-011 and TICKET-018.

### 2026-09-26 (release)
- Shipped in runtime 0.1.9, together with TICKET-018. 283,954,324 bytes, SHA-256 `8f4d4dda2358d767fcb84a4739c6533195cd9aaa80d6756735a531e43a33a68e`, notarization `a4e09740-e1ff-41ad-abed-7cb9b2556d5e`, Accepted with no issues, minimum macOS 14.0. Hosted on Hugging Face `onionmonster/cue-runtime` at commit `dcf288cca59483d3b562af9ad04403384c327e56`, with GitHub Release `runtime-0.1.9` as backup. The plugin pins both.
- Checks on the signed archive: the plugin's unpack script installed it into a scratch support folder, Gatekeeper accepts `ffmpeg` as a Notarized Developer ID, and the helper there reported 0.1.9 and listed E2B and E4B. E4B passed its trial on the spoken clip in 8.5 s and became the model in use, and switching back to E2B passed in 5.4 s. The archive downloaded from the pinned Hugging Face URL in 32 s with the same SHA-256.
- Existing installs keep their old runtime until TICKET-016.

## Testing
- Unit tests: a collapse in the middle and at the end, the prefix check, punctuation restored on a prefix, the minimum committed length, and no cue boundary that is not an aligner time.
- Real inference: the TICKET-017 session driver on the same film range, before and after, with reference-line coverage and hole time.
- `scripts/test` and `npm run build`.
