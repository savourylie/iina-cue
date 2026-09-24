# Development preview installation

This is a local developer preview, not the spec's finished zero-terminal installer. No model is bundled, downloaded automatically, or sourced from Eloquent. The project directory must stay in place.

## Existing machine

The isolated `.venv` and npm dependencies have been installed. `uv.lock` and `package-lock.json` pin them. `dist/Cue.iinaplugin-0.1.0.iinaplgz` was built by IINA's official CLI.

A development symlink already exists:

`~/Library/Application Support/com.colliderli.iina/plugins/plugin.iinaplugin-dev`

It points to this repository's `plugin/`. IINA visibly recognizes “Cue for IINA · Technical Preview”; it is **enabled for this approved local test**. Do not also install the archive alongside the development link: they share the same plugin identifier.

## Setup plan and permissions

- Read a user-selected local movie and write local PCM/cache/subtitle files.
- Run the project's Python helper with FFmpeg/FFprobe as argv processes.
- Bind a random **127.0.0.1-only** port, protected by a random bearer token and client/session IDs.
- Show IINA status and native dialogs. No microphone, screen recording, login agent, administrator access or cloud API.
- Download 3,564,002,544 bytes of pinned public weights after explicit consent; allow 7 GB for models/runtime. Source repositories and revision hashes are printed by `scripts/setup-models` and stored in `models/manifest.json`.
- Gemma terms: https://ai.google.dev/gemma/terms . Model setup must comply with those terms; this project cannot accept them on the user's behalf.

```sh
scripts/setup-models                    # print plan only
scripts/setup-models --accept-download  # only after consent/terms review
scripts/doctor
scripts/benchmark --media /absolute/path/test.mp4 --duration-ms 180000 --source en --mode zh-TW
```

This machine has passed the synthetic 3-minute pipeline benchmark. Enable Cue in IINA Settings → Plugins when testing it; natural-dialogue quality acceptance remains open. The helper path preference may stay empty on this machine; the bundle embeds the path to `scripts/cue-helper`. For another checkout, rebuild or set the absolute bootstrap path.

Once enabled, use Plugin → Cue → Open Cue sidebar and turn on the **AI subtitles** switch. Playback continues while subtitles are prepared, and the generated track attaches automatically when available. A preparation error appears in red beside the switch with a retry button. Turning the switch off stops Cue's subtitle work without changing playback. The Cue sidebar has an optional **Pause until captions are ready** checkbox, off by default; when enabled, press play after subtitles are ready. Cue never automatically resumes a user pause. **White text on a translucent black background** is on by default and affects only Cue's selected subtitle track; turning it off or stopping Cue restores the prior mpv subtitle style. **Subtitle size** changes the selected Cue captions live and restores the prior player size when Cue stops. Output defaults to the video's original spoken language; **Subtitle language** shows the detected language, for example **English (original)**, and can switch to Traditional Chinese, Simplified Chinese, English, Japanese, or Korean. Traditional and Simplified Chinese are separate translation and cache targets. The plugin menu offers the same output choices and a source language override. All plugin controls and messages are in English. Existing subtitles and source files are not overwritten.

**Source language** includes every language declared by the installed Qwen forced aligner: Chinese, Cantonese, English, German, Spanish, French, Italian, Portuguese, Russian, Korean and Japanese. Cantonese, German, Spanish, French, Italian, Portuguese and Russian are experimental in Cue. Manual selection also guides the Gemma transcription prompt; automatic language detection still relies on transcription text and may misclassify speech. The source list does not expand the tested subtitle output languages or establish transcription, alignment or translation quality for a whole movie. Cantonese may require manual selection because the text classifier does not distinguish it reliably from Chinese.

In IINA, expand **Advanced** near the bottom of the Cue sidebar, or open **Plugin → Cue for IINA · Technical Preview → Advanced** in the macOS menu bar. Both contain **Save a copy as MKV (reset timestamps)…**, **Export generated subtitles…**, and diagnostics. The macOS Advanced submenu appears above IINA's automatic **More…** group. Remux opens a folder picker, then shows a single-line `.mkv` filename field and the exact output path in the Cue sidebar. Press Enter or **Save copy** to begin, or **Cancel** (or Escape) to close the field. The filename is checked while you type; an existing file or a name with folders is reported under the field. While the copy runs, **Cancel** stops FFmpeg and deletes the temporary file; once saving has started, the copy finishes instead. A finished copy offers **Show in Finder**. The progress bar reports the percentage of the input timeline copied, followed by verification and saving; 100% appears only after success. FFmpeg copies video, audio, subtitle, and supported attachment streams without re-encoding; timed metadata/data streams are omitted because Matroska cannot contain them. Cue verifies the copied streams and near-zero start before exposing the new file. The original is never overwritten. This can correct a shifted container origin; it cannot repair every kind of damaged or discontinuous timestamp. A failed or interrupted copy may leave a hidden `.cue-remux-*` temporary file in the chosen folder to remove manually. Export writes the active session's generated SRT and a JSON coverage record at an absolute path you enter. Incomplete coverage produces a `.partial.srt` filename, and existing files are never overwritten.

## Diagnostics and native smoke

The Advanced menu provides a player/audio-track diagnostic and an explicit 100-reload diagnostic for a permitted local test movie. The latter creates clearly labeled dummy captions in the plugin data directory, reloads the same track, checks track presence/count and restores the prior subtitle choice if the user has not changed it. Its `@data/cue-smoke-results.json` reports only track-presence success; watch for visible flicker and verify pause behavior separately. It passed all 100 iterations in native IINA 1.4.4. Fullscreen/flicker acceptance remains open. **Save diagnostics** is also in Advanced; it writes `cue-session-diagnostic.json` without source paths, text or credentials.

`scripts/doctor` may report unavailable hardware fields when run under a restrictive sandbox. Run directly in Terminal for complete hardware detection. It never records machine serial numbers or UUIDs.

## Data and cleanup

Development runtime files are under `.runtime/`: private `connection.json`, bootstrap lock, SQLite cache, session SRTs, temporary audio, models and native compilation cache. Model weights are separate from subtitle cache. Audio temporary directories are removed after each successful/failed job. Crash cleanup and LRU enforcement need further work.

`scripts/cue-helper cache status` reports cache size. `cache clear --media /absolute/path/movie.mp4` clears that movie's source/target profiles only; stop its AI session first. Export from the active IINA session if multiple audio/profile versions are cached. Existing output paths are never overwritten.

`scripts/cue-helper shutdown` refuses while clients remain active. Stopping AI/closing the player relinquishes the session; client/session leases are the crash fallback. No shell startup files or global Python installations were changed.

To remove only the development link:

```sh
/Applications/IINA.app/Contents/MacOS/iina-plugin unlink plugin
```

Then reopen IINA. Do not delete dora, Hugging Face shared assets, other plugins, user movies or existing subtitles. The archive is unsigned; no signing or notarization was performed, and no Gatekeeper/SIP changes are needed or recommended.

During development, quit and reopen IINA after rebuilding. On IINA 1.4.4, Reload All Plugins produced duplicate sidebar tabs and closed IINA during testing. Normal installed use does not require reloading plugins.
On restart, Cue replaces an idle older helper automatically. If another Cue window or remux is still using it, close that window or wait for the remux to finish, then retry.

## Another Mac

This checkout requires an Apple Silicon Mac, IINA in `/Applications`, `uv`, Node/npm, and FFmpeg/FFprobe. It was validated on IINA 1.4.4. After cloning the repository, run from its root:

```sh
scripts/setup-dev
scripts/setup-models                 # review model sources, sizes and terms
scripts/setup-models --accept-download
scripts/test
/Applications/IINA.app/Contents/MacOS/iina-plugin link "$PWD/plugin"
```

Run the model download only after reviewing the terms and confirming enough disk space. Restart IINA, then enable Cue in IINA Settings → Plugins. The development link and built helper path belong to this new checkout; do not copy the old Mac's `.venv`, `.runtime`, model files, cache, generated fixtures, benchmark results or archive. They are intentionally excluded from Git. Do not install the archive and development link at the same time because they share one plugin identifier.
