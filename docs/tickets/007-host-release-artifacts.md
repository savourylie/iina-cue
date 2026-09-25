# [TICKET-007] Choose hosting for the runtime and publish a release manifest

## Status
`done`

## Dependencies
- Requires: #004 ✅

## Description
The plugin needs a stable place to download the notarized runtime archive (about 240 MB), plus a small machine-readable manifest. The manifest says which runtime version goes with which plugin version, and gives the archive's URL, size and SHA-256.

Publishing is outward-facing and must be explicitly approved by the user. AGENTS.md forbids publishing without that approval.

## Acceptance Criteria
- [x] The user has decided where the runtime is hosted, for example GitHub Releases on the project repository, and has approved publishing.
- [x] A release manifest, a static JSON file, lists for each runtime: version, URL, size, SHA-256, minimum macOS, architecture, and compatible plugin versions.
- [x] The plugin's `allowedDomains` list only the hosts it actually needs, including any redirect target used by the download host.
- [x] A test release is downloadable anonymously and its hash matches the manifest.

## References
- `plugin/Info.json` — `allowedDomains` currently lists only `127.0.0.1`.
- `docs/release-checklist.md` — existing release steps.

## Implementation Notes
- Required constraints: no credentials in the plugin; downloads over HTTPS only; archives are notarized (#004).
- Note: IINA's "Install from GitHub" updates plugins from GitHub releases, so hosting the runtime there keeps one release process.

## As-Built Notes

### 2026-09-25
- The user approved GitHub Releases on `savourylie/iina-cue` for this publish. Tag `runtime-0.1.5` carries the notarized archive from TICKET-004 (270,969,508 bytes, SHA-256 `70218fd01793d234d280401420aab1dfaf0ba874098a17a9479e3ffbaa91197f`). `release/runtime-0.1.5.json` records minimum macOS 27.0 and architecture arm64. Compatible plugin version is 0.1.0. `allowedDomains` adds `github.com`, `release-assets.githubusercontent.com`, and `objects.githubusercontent.com`, and keeps `127.0.0.1`. This archive is not a macOS 14 build.

### 2026-09-25 (runtime 0.1.6)
- Runtime 0.1.6 needs macOS 14.0 instead of 27.0. FFmpeg builds with `MACOSX_DEPLOYMENT_TARGET=14.0`, and uv installs the macOS 14.0 wheels of MLX and mlx-metal. numpy and scipy ship no wheels for older systems, so 14.0 is the floor. IINA 1.4.4 itself declares 10.15, and Apple Silicon Macs start at macOS 11. The build fails if any Mach-O file needs a newer system than 14.0.
- On this M1 Ultra, a 54 s English clip ran about 34–36 s warm on both 0.1.5 and 0.1.6. The two produced identical SRT files. The real smoke test passed on 0.1.6 in 10.7 s.
- Archive: 267,837,724 bytes, SHA-256 `4dea7f196f67dbcc34872bdb02eb2cfac54378c3e98da72754240f76f6186483`, notarization `25ba4407-fb9e-4401-8648-397db02256fc` (Accepted). A bare Mach-O file cannot carry a stapled ticket, so Gatekeeper checks online.
- Hosting moved to Hugging Face, `onionmonster/cue-runtime`, pinned to commit `ee592ca17f88074387a8f5486d915c6ab57007b6`. GitHub Release `runtime-0.1.6` holds the same file as a backup. On the same home connection, GitHub's release CDN gave about 124 KB/s (about 37 minutes for the archive) and Hugging Face gave 7.5–15.6 MB/s. The plugin tries Hugging Face, then GitHub. Both write one partial file, so either can resume it. `release/runtime-0.1.6.json` lists both URLs.
- The user created the Hugging Face repository and ran the upload; the Claude Code auto mode refused to create a public repository.
- Plugin install run outside IINA, from Hugging Face, with the real curl and unpack script: 33.5 s. No quarantine flag. `spctl` reports `accepted, source=Notarized Developer ID`.

## Testing
- `curl -L` the URL from the manifest on a machine without developer tools and confirm size and SHA-256.
