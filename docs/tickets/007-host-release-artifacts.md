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

## Testing
- `curl -L` the URL from the manifest on a machine without developer tools and confirm size and SHA-256.
