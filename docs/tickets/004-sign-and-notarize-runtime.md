# [TICKET-004] Sign and notarize the runtime archive

## Status
`blocked`

## Dependencies
- Requires: #001, #002, #003

## Description
On a Mac with SIP enabled, Gatekeeper blocks any unsigned helper binary that carries a quarantine flag, showing "Apple could not verify … is free of malware". Notarization is therefore a required safety net. This applies even though Cue's own downloads are not quarantined.

The 2026-09-24 trial signed all 250 Mach-O files in the runtime with "Developer ID Application: Calvin Ku (92QTH3YBHM)". That covered about 230 `.so` files, 16 `.dylib` files, `python3.12`, `ffmpeg` and `ffprobe`. They were signed with the hardened runtime, a secure timestamp and no entitlements. The trial:
- submitted through the `cue-notary` keychain profile, and Apple returned **Accepted** on the first submission;
- showed `spctl -a -t open --context context:primary-signature` reporting "Notarized Developer ID";
- produced subtitles identical to the unsigned runtime, so inference is unaffected.

## Acceptance Criteria
- [ ] A release step signs every Mach-O in the runtime, libraries first and executables last. It uses the hardened runtime and a secure timestamp, and passes `codesign --verify --strict`.
- [ ] It submits the runtime with `notarytool` through a keychain profile, waits for the result, saves Apple's log, and fails the release unless the status is Accepted.
- [ ] It produces the final versioned archive plus a manifest with its version, size, SHA-256 and minimum macOS.
- [ ] The notarized runtime passes a real benchmark with output identical to the unsigned build.

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
