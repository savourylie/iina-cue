# [TICKET-007] Choose hosting for the runtime and publish a release manifest

## Status
`blocked`

## Dependencies
- Requires: #004

## Description
The plugin needs a stable place to download the notarized runtime archive (about 240 MB), plus a small machine-readable manifest. The manifest says which runtime version goes with which plugin version, and gives the archive's URL, size and SHA-256.

Publishing is outward-facing and must be explicitly approved by the user. AGENTS.md forbids publishing without that approval.

## Acceptance Criteria
- [ ] The user has decided where the runtime is hosted, for example GitHub Releases on the project repository, and has approved publishing.
- [ ] A release manifest, a static JSON file, lists for each runtime: version, URL, size, SHA-256, minimum macOS, architecture, and compatible plugin versions.
- [ ] The plugin's `allowedDomains` list only the hosts it actually needs, including any redirect target used by the download host.
- [ ] A test release is downloadable anonymously and its hash matches the manifest.

## References
- `plugin/Info.json` — `allowedDomains` currently lists only `127.0.0.1`.
- `docs/release-checklist.md` — existing release steps.

## Implementation Notes
- Required constraints: no credentials in the plugin; downloads over HTTPS only; archives are notarized (#004).
- Note: IINA's "Install from GitHub" updates plugins from GitHub releases, so hosting the runtime there keeps one release process.

## Testing
- `curl -L` the URL from the manifest on a machine without developer tools and confirm size and SHA-256.
