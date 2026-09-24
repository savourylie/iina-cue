# [TICKET-005] Let the helper run from an installed runtime

## Status
`done`

## Dependencies
- Requires: None

## Description
The helper currently assumes the project checkout:
- `PROJECT` is derived from the source path;
- `.runtime/` and the models live inside the repository;
- FFmpeg is looked up in Homebrew first;
- the plugin launches the shell script `scripts/cue-helper`, whose absolute path is baked in at build time.

An installed Cue must instead run entirely from a per-user location and use only its bundled FFmpeg.

## Acceptance Criteria
- [x] In installed mode, cache, logs, connection file and models default to a per-user directory outside the plugin package, such as `~/Library/Application Support/Cue`. Development mode keeps working unchanged.
- [x] In installed mode, `binary("ffmpeg")` and `binary("ffprobe")` resolve only to the runtime's own binaries and never fall back to Homebrew or `PATH`.
- [x] The plugin starts the helper without executing any script or binary shipped inside the `.iinaplgz`. It either runs the notarized runtime Python directly, or runs a runtime-provided script through `/bin/sh`.
- [x] The plugin finds the installed runtime without a build-time absolute path to the developer's checkout, and reports `SETUP_REQUIRED` when the runtime is missing.
- [x] Existing helper and plugin tests pass, and new tests cover installed-mode path and FFmpeg resolution.

## References
- `helper/src/cue/bootstrap.py` — `PROJECT`, `runtime_root()`, `models_root()` and `ensure()`.
- `helper/src/cue/media.py` — `binary()` search order.
- `plugin/src/client.ts` — bootstrap lookup via `CUE_BOOTSTRAP_DEFAULT` and the `bootstrap` preference.
- `scripts/build-plugin.mjs` — where `CUE_BOOTSTRAP_DEFAULT` is baked in.
- `scripts/cue-helper` — current launcher.

## Implementation Notes
- Required constraints: keep one persistent inference subprocess; keep the bootstrap lock and version handshake; the plugin package contains no Mach-O files, dylibs or directly executed scripts. JS and HTML are fine: on the SIP-enabled test Mac, quarantined plugin JS ran while a quarantined binary was blocked.
- Suggested approach: select installed mode with an environment variable or marker file written by the installer, rather than guessing from paths.

## Testing
- `scripts/test` and `npm run build`.
- With a runtime from #001 installed under Application Support, start playback in IINA with no Homebrew FFmpeg on `PATH`. Captions must appear, and `helper.log` must show the bundled FFmpeg path.

## As-Built Notes

### 2026-09-24
- Installed mode is on when `CUE_INSTALLED` is `1`, `true`, or `yes`, or when a regular file `installed` exists under the support directory. `CUE_INSTALLED=0` forces development mode. `scripts/cue-helper` exports `0`, and `helper/tests/conftest.py` does the same for pytest, so this checkout keeps using `.runtime` after an install exists.
- With `CUE_HOME` and `CUE_MODELS` unset, installed data defaults to `~/Library/Application Support/Cue`: `connection.json`, `helper.log`, `bootstrap.lock`, and `cache/` live there, and models live in `models/`. The relocatable tree is `runtime/` (`python/bin/python3.12`, `bin/ffmpeg`, `bin/ffprobe`, `bin/cue-helper`). #008 should unpack only `runtime/` and write the `installed` marker, so a runtime swap does not delete models or the cache. `CUE_SUPPORT` overrides the support directory for tests. Explicit `CUE_HOME` and `CUE_MODELS` still win. This is the single directory named by this ticket. The older spec's split across Caches and Logs under "IINA AI Subtitles" is not this layout.
- In installed mode, `binary()` returns only `<support>/runtime/bin/ffmpeg` or `ffprobe`. It rejects a symlink, a non-executable file, and any other name. It does not consult `CUE_FFMPEG_BIN_DIR`, Homebrew, or `PATH`. Development mode still honors `CUE_FFMPEG_BIN_DIR` as a pinned directory with no fallback, then the old search order. `doctor` uses the same resolution. The supervised helper writes one `{"event":"ffmpeg","path":...}` line to `helper.log`.
- IINA's `utils.exec` replaces the process environment with `LC_ALL` only. With the file-system permission, `file.exists` and `utils.resolvePath` expand `~/` (`JavascriptAPI.parsePath`). Arguments are not expanded, so the plugin resolves the launcher to an absolute path and runs `/bin/sh` on `runtime/bin/cue-helper`. That script exports `CUE_INSTALLED=1` and fills in `HOME` when it is unset. Python also fills in `HOME` at import when it is unset. A runtime built before the script exists is started as `runtime/python/bin/python3.12 -m cue.cli ensure`. A marker with no runtime raises `SETUP_REQUIRED` and does not run the baked checkout path. A non-empty absolute `bootstrap` preference still wins. `scripts/build-runtime` copies `scripts/runtime-cue-helper` to `bin/cue-helper`, and `models/manifest.json` to `manifest.json`, before the path scan. The development plugin build still embeds this checkout's `scripts/cue-helper` for machines without the marker.
- The installed helper reads `<support>/runtime/manifest.json`. Development keeps `models/manifest.json` in the checkout, so profile hashes do not change. `ensure` raises `SETUP_REQUIRED` before starting a helper when that installed manifest is missing. An already-built runtime does not contain the launcher or the manifest until `scripts/build-runtime` is run again.

### 2026-09-25
- The single directory `~/Library/Application Support/Cue` is the agreed layout. The spec's split across Application Support, Caches, and Logs under "IINA AI Subtitles" stays unused. Cache, logs, the connection file, and models are siblings under that one directory; the relocatable tree is `runtime/`.
- This branch was fast-forwarded from `bf988fd` to `7f32830` before the remaining edits, so the license notices and signing work stay in the tree.
- `scripts/test` passed: 134 pytest tests and 34 plugin tests, then `npm run build`. The packed `.iinaplgz` contains only `Info.json`, HTML, and JavaScript. With `PATH=/usr/bin:/bin`, a temporary support directory, and the static FFmpeg binary copied into `runtime/bin`, the helper started and `helper.log` recorded that bundled path. Playback in IINA was not run, so captions were not observed.
- The first IINA launch failed before the helper started. `resolvePath` had been copied off `iina.utils` and called as a bare function, which JavaScriptCore rejects with `TypeError: self type check failed for Objective-C instance method`. It is now called on `iina.utils`. The plugin bundle was rebuilt in place.
- After that fix, captions appeared in IINA in about 8 seconds. `helper.log` recorded `~/Library/Application Support/Cue/runtime/bin/ffmpeg` for that session. The helper process was the runtime's `python3.12`, not the checkout `.venv`. Homebrew was not on the helper's `PATH` because IINA's `utils.exec` keeps only `LC_ALL`.
