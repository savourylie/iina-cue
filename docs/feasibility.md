# Feasibility — 2026-09-23

A real local vertical slice is implemented. The full v1 acceptance gate remains open. The user approved model download; pinned assets are installed and verified.

## Actual environment

Apple M3 Max, 14 CPU / 30 GPU cores, 36 GB RAM; macOS 27.2; IINA 1.4.4 / embedded mpv v0.38.0; FFmpeg 9.0.2; isolated CPython 3.12.11. No machine serial or UUID is retained.

## Measured pipeline

Self-authored scripts were synthesized using installed macOS voices. `scripts/make-speech-fixtures.py` reproduces them without discovering private media. The long English sample is 180.128 seconds. Measurements include extraction, model loading, ASR, language work, forced alignment, cue assembly, translation, and SRT persistence; they exclude native IINA install ack and deliberate high-water idle.

| Output | Cold | Warm | Warm RTF | Warm seconds / media minute |
|---|---:|---:|---:|---:|
| Traditional Chinese | 55.81 s | 51.28 s | 0.285 | 17.1 s |
| Original English | 31.75 s | 30.74 s | 0.171 | 10.2 s |

The translated run's first committed batch took 5.49 s cold / 2.41 s warm. Warm stage totals: extraction 0.92 s, ASR 21.42 s, alignment 3.33 s, translation 25.57 s. Peak process RSS was 2.21 GB; **this excludes some Metal/native allocations and is not total model memory**. The translated timing run preceded native playback tests. The original-mode run was taken during development, so it is not an isolated performance comparison. These synthetic results are neither a dense natural-dialogue acceptance set nor a same-clip comparison against dora.

Reproducible commands and detailed batch outputs:

- `scripts/benchmark --media benchmarks/fixtures/generated/en-long.wav --duration-ms 180128 --mode zh-TW --source en --output benchmarks/results/local-litert-3min`
- Equivalent `--mode original --output benchmarks/results/local-litert-original`.
- `.venv/bin/python scripts/probe-languages.py`: en/zh/ja/ko each completed real ASR, independent text LID, forced alignment and translation. All four LID results agreed with the generated source language. **Korean contains a recognition error in the final sentence**; pipeline execution is not language-quality acceptance. `benchmarks/results/languages.json` preserves actual output.

## Native IINA evidence

The development plugin is recognized and enabled. `benchmarks/results/iina-renderer-smoke.json` records 100 real sub-add/sub-reload updates with one subtitle track, stable ID 1, mpv v0.38.0, selected audio mpv ID 1 / FFmpeg index 1, and playback remaining paused. This is track-presence evidence, not a frame-by-frame flicker measurement.

The real plugin launched its own helper, generated Traditional Chinese subtitles, installed them in mpv, and captions were visibly observed on the test video. Startup ordering, the sidebar message bridge, cache partition reuse and render-ack races were fixed during native testing. The final patched build was restarted in IINA: seeking from 36 s to 80 s joined disjoint installed ranges into continuous 19.833–181.167 s coverage; subsequent seeks to 125 s and back to 30 s stayed ready with no error. Playback resumed with a visible Traditional Chinese caption, then paused again. See `benchmarks/results/iina-final-seek.json`.

A second self-generated video contains separate English and Japanese audio tracks (FFmpeg stream indexes 1 and 2). Native IINA switching English → Japanese → English created a new ready subtitle session for each selected track and returned to the English cached range. Selecting subtitle “None” manually stopped AI and left that choice in place. See `benchmarks/results/iina-two-audio.json`; this is track/session behavior evidence, not natural-speech quality acceptance.

## Failures found and corrected

- The 2.01 GB `-gpu.litertlm` artifact lacks the audio encoder. The same E2B revision's full 2.59 GB multimodal artifact works with GPU language / CPU audio backends. Hashes and rejected-file evidence remain in the manifest.
- LiteRT requires its compilation-cache directory to exist; the adapter now creates it.
- Qwen's 80 ms resolution sometimes yields zero-length function words. At most three collapsed tokens can share adjacent measured outer boundaries; collapsed runs and large conflicts are rejected. Across windows, overlap up to 160 ms may reuse a previous measured cue end; no average word timings are invented. Both operations are counted in batch diagnostics.
- Copying long opaque hashes caused a translation schema failure. Requests now use short validated aliases, restored to stable source IDs only after exact-set validation.
- High water controls whether to schedule a bounded window, not whether to truncate it into a sub-second alignment tail. Maximum lookahead can exceed the 60 s target by one 16 s job.
- Starting a new target in a cached source chunk reuses the complete aligned chunk. It no longer writes a second overlapping source partition. A cache conflict becomes a session error rather than terminating the supervisor.
- Native sidebar initialization waits for the window-loaded event or a user action. The WebKit message API retains its receiver.

## Other evidence and remaining gates

`scripts/test` includes meaningful regression tests, real FFmpeg timing/mapping fixtures and localhost security. `.venv/bin/python scripts/integration-smoke.py` uses real processes and digital silence: four concurrent bootstraps give one helper; high water stops at 74 s; a seek to 77 s adds a separate range ending at 80 s. This does not measure GPU responsiveness.

Not yet accepted: natural speech quality / boundary accuracy; music and quiet-speech negatives; Silero VAD; 20-minute playback and load impact; fullscreen/PiP flicker; complete Metal memory; zero-terminal installer; LRU budget; sleep/wake recovery; signed distribution. There is no fake backend, model-size upgrade, Whisper substitution or cloud fallback.

The exact failing native boundary at 88.673 s rejected a 16 s span (collapsed alignment units). The bounded retry, 8 s with 2 s context, passed; see `native-boundary-probe.json`. Successful HTTP snapshots may include a background inference error and still have usable installed coverage; the client preserves both. Native modal dialogs can suspend JavaScript timers and expire a lease; the client now reconnects and creates a session at the current position. The unlocked final native rerun passed seek, joined-coverage, cache-return, visible-caption and pause checks. A 48 s native modal wait then expired the 45 s lease; the plugin observed CLIENT_REQUIRED and rebuilt a ready session at the same 42.625 s position with the subtitle selected and playback paused. See `iina-native-reconnect.json`. A second inference failure and OS sleep/wake were not exercised in the native app.

`scripts/speech-integration-smoke.py` passed real helper/model processing on the exact native boundary cache. The failed boundary recovered, the gap before 121.458 s was filled into continuous coverage, and changing to original output reused aligned source (no ASR/alignment repeat). Local API latency during this test: p95 2.15 ms, maximum 48.28 ms. Its render acknowledgements are simulated; native evidence is kept separate.

A user-selected local 14:03 interview exposed a separate translation failure. At 20.020 s, the previous zh-TW build retained only 19.311–28.071 s and reported `TRANSLATION_FAILED: target script absent`; the next real source chunk included a numeric-only cue `14`. Requiring **every** translated cue to contain Han characters rejected valid number-only subtitles and halted later work. Validation now requires Han somewhere in a batch containing speech, while permitting individual numeric cues. The rebuilt plugin's native zh-TW session reached 19.311–92.335 s with no error and preserved `14`. The sidebar offers original/zh-TW/en, with original as the default; native original captions remained visible after the old failure position.

A sequential helper check then found an independent `ALIGNMENT_FAILED: cached right boundary text mismatch` near 414.775 s while joining a previously generated 420.003 s chunk. Overlapping audio context can yield different ASR wording for a unit that straddles the already committed right boundary. The pipeline now discards only those crossing units, records their count, and never invents an end time or changes the cached right-hand cues. The corrected helper processed from 20 s to the 843.465 s end with no error; render acknowledgements in that helper check were simulated. IINA then loaded continuous 19.311–843.465 s original-language coverage, with the subtitle track selected and a visible caption at 13:55. See `benchmarks/results/user-video-sequential.json` and `user-video-regression.json`. This does not establish an uninterrupted native 14-minute watch or language quality. Final suite: 52 Python + 9 TypeScript tests passed.
