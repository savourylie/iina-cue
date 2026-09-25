# [TICKET-014] Publish the plugin release

## Status
`pending`

## Dependencies
- Requires: #013 ✅

## Description
TICKET-012 tests two install routes, and neither has a plugin to install yet:
- double-clicking a `.iinaplgz` downloaded with a browser;
- IINA's "Install from GitHub" with `savourylie/iina-cue`.

This ticket publishes the general-user pack from TICKET-013 as a GitHub Release on `savourylie/iina-cue`, so both routes can be tested. The runtime is already published separately: `runtime-0.1.6` on Hugging Face `onionmonster/cue-runtime`, with a GitHub Release as backup.

## Acceptance Criteria
- [ ] How IINA's "Install from GitHub" finds a plugin is confirmed from IINA's documentation or source and recorded here. For example: does it use a release asset or the repository layout, which release does it choose, and does it read `ghRepo`/`ghVersion` from `Info.json` for updates?
- [ ] The user explicitly approves the publish at the time it happens.
- [ ] A GitHub Release carries the general-user `.iinaplgz`. Its tag does not collide with the `runtime-*` tags, and IINA does not mistake a runtime release for a plugin release.
- [ ] Downloading the `.iinaplgz` from the release page in a browser gives a file whose SHA-256 matches the local build.
- [ ] On this Mac, "Install from GitHub" with `savourylie/iina-cue` finds the plugin release. Run this in a separate IINA profile, or restore the existing Cue install afterwards.

## References
- `docs/install-cue.md`: both install routes as the user reads them.
- `release/runtime-0.1.6.json`, `docs/tickets/007-host-release-artifacts.md`: existing release naming and hosts.
- `plugin/Info.json`: plugin version and identifier `io.iina.cue`.

## Implementation Notes
- Required constraints: publishing is outward-facing. Do not publish without the user's explicit approval at the time (AGENTS.md). Claude Code auto mode may refuse the publish; then give the user the exact `gh release create` command.
- Required constraints: runtime releases stay `runtime-<version>`. Choose a distinct plugin tag, for example `v0.1.0` or `plugin-0.1.0`, after checking what IINA expects.
- Suggested approach: if IINA picks the repository's latest release, the runtime backup releases may need to be marked as not latest, or moved. Check this before publishing.

## Testing
- Browser download of the release asset, then `shasum -a 256` compared with the local build.
- "Install from GitHub" in IINA on this Mac, without disturbing the existing Cue install. Full clean-Mac verification belongs to TICKET-012.
