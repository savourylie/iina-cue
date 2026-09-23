# Acceptance matrix — 2026-09-23

Scope: local uncommitted 0.1.0 developer preview. A pass applies only to the named test, not the whole specification. All measurements are from this M3 Max. No release/tag or remote publication was created.

| Check | Status | Evidence / limit |
|---|---|---|
| Doctor, exact model/dependency identities | pass | doctor.json, manifest, uv.lock; approved assets downloaded and verified |
| Strict TypeScript + official packaging | pass | scripts/test, npm run build |
| IINA discovery and enabled native entry | pass | IINA 1.4.4, mpv v0.38.0 |
| LiteRT E2B real audio/text | pass | full multimodal artifact; local-litert-audio and local-litert-3min |
| Qwen forced alignment on Apple Silicon | pass on fixtures | real aligned units; no guessed/average timestamps |
| en/zh/ja/ko ASR/LID/alignment/translation | pass pipeline only | languages.json; Korean final sentence contains ASR errors |
| 3-minute full cold/warm pipeline | pass synthetic fixture | 55.81 / 51.28 s translated; warm RTF 0.285 |
| Original subtitle performance | measured | 31.75 / 30.74 s; warm RTF 0.171 |
| Natural-dialogue recognition, timing and translation quality | not accepted | Synthetic diagnostics do not establish quality or superiority to dora |
| FFmpeg audio mapping, delayed audio, nonzero origin | pass generated tests | Audio ID and ff-index remain distinct |
| Real helper + model + native caption display | pass observed vertical slice | IINA automatically launched helper; actual Traditional Chinese captions visibly rendered |
| 100 native reloads, no track accumulation | pass presence only | iina-renderer-smoke.json, one stable owned track; paused remained true |
| Native prepared and installed coverage | pass observed | iina-live-ready.json: both disjoint ranges retained; ready=true; 60 s buffer |
| Native reopening cached subtitles | pass observed | iina-cache-ready.json; final seek back to 30 s retained installed coverage |
| Final patched build native seek/cache join | pass on synthetic fixture | iina-final-seek.json: restart/re-enable, 80 s seek joined a cache hole into 19.833–181.167 s coverage, then 125 s and 30 s seeks retained ready subtitles; visible caption after resume; no error |
| Expired local client lease and native reconnect | pass on synthetic fixture | iina-native-reconnect.json: 48 s modal wait exceeded 45 s lease; CLIENT_REQUIRED triggered a new session at 42.625 s; installed range, selected subtitle and paused state recovered |
| Cross-window shared worker, auth and fencing | pass targeted tests | Concurrent bootstrap, client ownership, epochs, ack hashes, source/target isolation |
| Alignment failure retry | pass exact native boundary | 16 s span rejected, 8 s with 2 s context succeeded; native-boundary-probe.json |
| High-water stop and seek hole preservation | pass real silent service | control-integration.json; 74 s stop, separate 77–80 s range |
| Speech retry, cache-hole joining, target switching | pass real helper/model test | speech-integration.json; joined 19.833–181.167 s; original output reused aligned source; simulated client ack only |
| User-selected 14:03 local video, numeric-cue translation regression | pass reproduced boundary | user-video-regression.json: old zh-TW session failed after 28.071 s with TRANSLATION_FAILED; corrected build installed through 92.335 s with no error |
| Same video, cached-right-boundary joining | pass real helper from 20 s to end | user-video-sequential.json: old build failed near 414.775 s; corrected helper reached 843.465 s with no error and simulated render acks; native IINA installed 19.311–843.465 s and showed original caption at 13:55. Uninterrupted native watch remains open |
| Source-chunk reuse inside a new target | pass regression | Complete aligned partition reused; conflicts isolated to session |
| Background failure keeps usable installed coverage | pass transport regression | Successful session error is not treated as an HTTP error |
| Native user pause | observed | Startup and renderer smoke remain paused; no auto-resume policy |
| Default play-through and automatic subtitle attachment | pass observed on new synthetic media | Cue enabled while IINA played; native diagnostic reported `paused=false`, installed coverage and selected Cue track as inference progressed |
| Optional wait-for-subtitles pause | pass observed on new synthetic media | Sidebar checkbox enabled before starting a fresh media signature; player paused during preparation and remained paused after ready; checkbox restored to off |
| Semi-transparent black box with white text | pass observed in IINA 1.4.4 / mpv 0.38.0 | Cue caption visibly rendered over black translucent box on synthetic and user-named videos; unchecking restored prior outlined text, rechecking restored box; `sub-back-color` and `sub-shadow-offset` use the version-compatible mpv options |
| Live subtitle-size slider | pass observed in IINA 1.4.4 | On the user-named video, moving Subtitle size from 55 to 82 enlarged the visible Cue caption immediately; the value was returned to 55 afterward. Unit tests cover restoring the prior player size and preserving a later manual change |
| English plugin interface and detected original label | pass observed / source check | Sidebar, menu, preferences, status and diagnostic messages are English; a cached English source displays **English (original)** after reload. `originalLanguageLabel` tests also cover Chinese, Japanese, Korean and unknown |
| Japanese and Korean output choices | pass local pipeline and native display | `local-ja-preview` and `local-ko-preview` each translated 8.069 s of English fixture speech with stable source timings; both languages were selected and visibly rendered on the user-named video in IINA. Natural-dialogue translation quality is not accepted |
| Simplified Chinese output choice | pass local pipeline and native display | `local-zh-cn-preview` converted 11.604 s of Traditional Chinese fixture speech to Simplified Chinese (`火車` → `火车`) without changing aligned timestamps; selecting Simplified Chinese in IINA showed Simplified Chinese captions on the user-named video. Traditional and Simplified targets have separate cache profiles. Natural-dialogue translation quality remains open |
| Native audio-track switch and manual subtitle selection | pass on synthetic fixture | iina-two-audio.json: English stream 1 → Japanese stream 2 → English stream 1 each reached ready with selected subtitle; manual None stopped AI and remained selected |
| VAD/music/quiet speech quality | not_run | Only digital-zero silence bypass implemented; no Silero |
| Fullscreen/PiP flicker, 20-minute playback, load impact | not_run | No claims |
| ≤10 s warm first installed subtitles | not accepted | First synthetic pipeline batch 2.41 s warm excludes native ack |
| Total memory including Metal | not_run | Process RSS is incomplete |
| LRU budget, full wake/crash recovery | incomplete | Leases and reconnect exist; full OS lifecycle matrix open |
| Zero-terminal install, signing, update, rollback | not_run | Machine-bound developer setup, not redistributable app runtime |

The final v1 AC-01 through AC-15 set is **not accepted as complete**. This preview establishes a functioning local model/player path while preserving explicit remaining gates. Installation of models was authorized; no consent is still pending. No private videos were discovered or uploaded; the video explicitly named by the user was tested locally.
