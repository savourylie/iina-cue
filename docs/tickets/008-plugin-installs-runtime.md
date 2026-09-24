# [TICKET-008] Plugin installs, verifies and updates the runtime

## Status
`blocked`

## Dependencies
- Requires: #005, #007

## Description
Before the Python helper exists, only the plugin's JavaScript can fetch it. The plugin must check that the Mac can run Cue, then download the runtime archive into a per-user location, verify it, unpack it, and keep it matched to the plugin version.

The IINA probe on 2026-09-24 established how:
- files fetched with `iina.http.download` or `/usr/bin/curl`, and files extracted from them with `/usr/bin/tar`, carry no quarantine flag;
- files inside a browser-downloaded `.iinaplgz` keep the quarantine flag after IINA installs them, and quarantined unsigned binaries are blocked on a SIP-enabled Mac;
- downloading and unpacking the 239 MB runtime inside IINA took 14 seconds from a local server.

## Acceptance Criteria
- [ ] The preflight check refuses with a clear reason on Intel Macs, macOS older than 14, IINA older than 1.4, insufficient free disk space, or less RAM than a configurable threshold. The threshold defaults to 16 GB until #011 decides otherwise.
- [ ] The runtime download resumes after interruption, verifies SHA-256 against the release manifest, and is unpacked atomically. A failed or partial install never replaces a working runtime.
- [ ] After install, the runtime binaries are not quarantined, and the helper starts from them.
- [ ] When the plugin requires a newer runtime version, it is fetched and swapped in only while no MKV copy or session is using the old helper, reusing the existing `HELPER_RESTART_REQUIRED` handshake.
- [ ] A build-time test fails if the packaged `.iinaplgz` contains any Mach-O file, dylib or executable script.

## References
- `plugin/src/client.ts` — helper bootstrap and `SETUP_REQUIRED`.
- `scripts/build-plugin.mjs` — plugin packaging with IINA's `iina-plugin pack`.
- `helper/src/cue/bootstrap.py` — `HELPER_VERSION` handshake and restart rules.
- `plugin/Info.json` — `permissions` and `allowedDomains`.

## Implementation Notes
- Required constraints: no Terminal steps for the user; never execute anything from inside the plugin package; downloads only after the user starts setup.
- Suggested approach: use `/usr/bin/curl -C -` for resumable downloads, or `iina.http.download` if it can resume. Unpack with `/usr/bin/tar` into a temporary sibling directory, then rename it into place.
- IINA's install dialog warns that the plugin "can execute other programs or applications that can harm your computer". This is unavoidable with the `file-system` permission and is covered in the install guide (#010).

## Testing
- Unit tests for preflight decisions and manifest or hash handling.
- Manual: in IINA, interrupt the download, resume it, and confirm verification. Corrupt the archive and confirm it is rejected. Run `xattr -p com.apple.quarantine` on installed binaries and confirm the attribute is absent.
