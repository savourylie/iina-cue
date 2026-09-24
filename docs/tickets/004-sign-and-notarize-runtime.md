# [TICKET-004] Sign and notarize the runtime archive

## Status
`done`

## Dependencies
- Requires: #001 ✅, #002 ✅, #003 ✅

## Description
On a Mac with SIP enabled, Gatekeeper blocks any unsigned helper binary that carries a quarantine flag, showing "Apple could not verify … is free of malware". Notarization is therefore a required safety net. This applies even though Cue's own downloads are not quarantined.

The 2026-09-24 trial signed all 250 Mach-O files in the runtime with "Developer ID Application: Calvin Ku (92QTH3YBHM)". That covered about 230 `.so` files, 16 `.dylib` files, `python3.12`, `ffmpeg` and `ffprobe`. They were signed with the hardened runtime, a secure timestamp and no entitlements. The trial:
- submitted through the `cue-notary` keychain profile, and Apple returned **Accepted** on the first submission;
- showed `spctl -a -t open --context context:primary-signature` reporting "Notarized Developer ID";
- produced subtitles identical to the unsigned runtime, so inference is unaffected.

## Acceptance Criteria
- [x] A release step signs every Mach-O in the runtime, libraries first and executables last. It uses the hardened runtime and a secure timestamp, and passes `codesign --verify --strict`.
- [x] It submits the runtime with `notarytool` through a keychain profile, waits for the result, saves Apple's log, and fails the release unless the status is Accepted.
- [x] It produces the final versioned archive plus a manifest with its version, size, SHA-256 and minimum macOS.
- [x] The notarized runtime passes a real benchmark with output identical to the unsigned build.

## References
- `docs/runtime-decision.md` — runtime composition.
- `helper/src/cue/bootstrap.py` — `HELPER_VERSION`, used to decide when an installed runtime is stale.

## Implementation Notes
- Required constraints: never store Apple credentials in the repository; use the keychain profile (currently `cue-notary`). Add entitlements only if a test proves they are needed.
- Open decision: loose command-line binaries cannot be stapled, so Gatekeeper checks their ticket online when they are quarantined. Cue's own downloads are unquarantined. For users who fetch the runtime manually, consider wrapping it in a stapled pkg or dmg.
- The trial script is in the session scratchpad only. Rebuild it as a project script (proposed: `scripts/release-runtime`).

## Testing
- Run the release step and confirm `notarytool` reports Accepted and the log lists no errors.
- Run `spctl -a -t open --context context:primary-signature -vv` on `python3.12`, `ffmpeg` and one MLX `.so`; each must report "Notarized Developer ID".
- Run the benchmark and compare with the unsigned output.

## As-Built Notes

### 2026-09-24
- `scripts/release-runtime` signs every Mach-O in `dist/runtime-<HELPER_VERSION>/`, libraries first and the three executables last. The identity is `Developer ID Application: Calvin Ku (92QTH3YBHM)`, with the hardened runtime, a secure timestamp, and no entitlements. Apple credentials stay in the `cue-notary` keychain profile. The script refuses an Apple Development certificate.
- Notarization submission `b7a14d9a-b72d-4e61-affd-dc2c0feb2c03` was Accepted. Apple's log says "Ready for distribution" and `issues` is null. `spctl` reports "Notarized Developer ID" for `python3.12`, `ffmpeg`, and `mlx/core.cpython-312-darwin.so`. The signed `python3.12` inside the archive still passes `codesign --verify --strict`.
- `stapler` cannot staple these loose binaries (error 73 on `ffmpeg`). The release does not wrap them in a pkg or dmg. Gatekeeper uses Apple's online ticket. That packaging choice stays open.
- The local manifest is `dist/runtime-<version>.manifest.json`. It records version, filename, size, SHA-256, minimum macOS, architecture, and the notarization receipt. It has no download URL. Hosting remains #007. This run: version 0.1.5, 270,969,508 bytes, SHA-256 `70218fd01793d234d280401420aab1dfaf0ba874098a17a9479e3ffbaa91197f`, minimum macOS 27.0, arm64.
- `minimum_macos` is the highest `LC_BUILD_VERSION` in the tree, not a chosen deployment target. FFmpeg and ffprobe are 27.0 because #002 did not set one. MLX's binaries are 26.2. The manifest does not claim macOS 14.
- A fresh `scripts/build-runtime` failed its path scan: current uv writes a three-line `/bin/sh` launcher and puts the absolute interpreter on the second line. The old rewrite only looked at the first line, so the build path stayed in `python/bin`. The rewrite now replaces that launcher with the relative one. The rebuilt runtime has `licenses/` and no build-machine path in those scripts.
- The notarized runtime needed no entitlements. On this Mac, a 10.31-second synthetic English clip produced the same source cues, rendered cues, and cue ids as the unsigned runtime. Wall-clock time was not compared. No archive was published.
