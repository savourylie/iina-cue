# [TICKET-005] Let the helper run from an installed runtime

## Status
`pending`

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
- [ ] In installed mode, cache, logs, connection file and models default to a per-user directory outside the plugin package, such as `~/Library/Application Support/Cue`. Development mode keeps working unchanged.
- [ ] In installed mode, `binary("ffmpeg")` and `binary("ffprobe")` resolve only to the runtime's own binaries and never fall back to Homebrew or `PATH`.
- [ ] The plugin starts the helper without executing any script or binary shipped inside the `.iinaplgz`. It either runs the notarized runtime Python directly, or runs a runtime-provided script through `/bin/sh`.
- [ ] The plugin finds the installed runtime without a build-time absolute path to the developer's checkout, and reports `SETUP_REQUIRED` when the runtime is missing.
- [ ] Existing helper and plugin tests pass, and new tests cover installed-mode path and FFmpeg resolution.

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
