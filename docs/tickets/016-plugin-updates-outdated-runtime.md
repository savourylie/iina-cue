# [TICKET-016] Plugin replaces an outdated runtime

## Status
`pending`

## Dependencies
- Requires: #008 ✅

## Description
The plugin installs the runtime only when the helper cannot answer. Once any runtime is installed, it keeps using it forever. A newer runtime, such as 0.1.7 with Silero VAD from TICKET-015, never reaches an existing install, including this Mac, which has 0.1.6.

TICKET-008 lists "When the plugin requires a newer runtime version, it is fetched and swapped in only while no MKV copy or session is using the old helper" as met. On 2026-09-25, `plugin/src` had no comparison of the helper's version, so that part was not delivered. The helper already reports `helper_version` from `ensure` and in the connection file.

## Acceptance Criteria
- [ ] The plugin knows the runtime version it requires. When the running helper reports an older `helper_version`, setup offers an update. It explains the download size and does not start without the user pressing a button.
- [ ] The update never replaces the runtime while a session or an MKV copy uses it. It reuses the `HELPER_RESTART_REQUIRED` rule (`maySwap`), and it stops the old helper before swapping.
- [ ] The update keeps the downloaded models and the subtitle cache. A failed download or a checksum mismatch leaves the old runtime working.
- [ ] A helper that is the same version or newer is left alone. A development checkout, or an explicit `bootstrap` preference, is never replaced.

## References
- `plugin/src/runtime-install.ts`: `installPublishedRuntime`, `maySwap`, and the unpack script's rename and rollback.
- `plugin/src/setup-controller.ts`: when the runtime is installed.
- `plugin/src/client.ts`: the `ensure` result and `Connection`.
- `helper/src/cue/bootstrap.py`: `HELPER_VERSION`.
- `docs/tickets/008-plugin-installs-runtime.md`: the original acceptance item.

## Implementation Notes
- Required constraints: never resume a user pause, and never interrupt playback without a user action (AGENTS.md).
- Suggested approach: compare `connection.helper_version` with a required version kept beside `RUNTIME_ARCHIVE_URLS`. Show an "Update Cue's helper" card state with its size, and then run the existing install path.

## Testing
- Unit tests with a stub `iina.http` and `exec`: an older helper leads to the update card, the same version does not, a busy helper refuses the swap, and a checksum failure keeps the old runtime.
- Manual: with runtime 0.1.6 installed, a plugin requiring 0.1.7 updates it in IINA, and captions still work afterwards.

## As-Built Notes

### 2026-09-26
- The plugin requires `RUNTIME_VERSION` (0.1.9), kept beside `RUNTIME_ARCHIVE_URLS`. A test holds it equal to the pinned `release/runtime-<version>.json`, its URLs and checksum, and the checkout's `HELPER_VERSION`.
- `planLaunch` now records how it started the helper: `preference`, `installed` or `development`. `ensure` keeps the `helper_version` from the connection, which every published runtime already reports. The setup controller offers an update only for the `installed` mode, and only when the reported version is older. The same or a newer version, a missing version, a development checkout and a helper chosen in preferences are left alone.
- The offer is a card, "Update Cue's helper", with the download size (284 MB). The normal controls stay usable, because the installed helper still works. Nothing starts until the user presses Update. While the update runs, the card replaces the controls, as first-run setup does. A failed or refused update shows the controls again, with the reason and Retry.
- Order of an update: this window's own session or MKV copy refuses first (`maySwap`). Then the archive downloads while the old helper keeps serving captions, and its SHA-256 is checked. Only then does `stopHelper` release this window's lease and ask the helper to shut down. The helper's own `/v1/shutdown` refuses with `CLIENTS_ACTIVE` or `REMUX_ACTIVE` while any window or MKV copy uses it, and then nothing is replaced. That covers other windows, whose sessions one plugin instance cannot see. After the helper exits, the existing unpack script swaps `runtime/` with its rename and rollback. The next request starts the new helper, and the spoken test clip runs before Cue calls itself ready.
- Only `runtime/` and the `installed` marker change. `models` (on this Mac, a symlink to this checkout's models) and `cache` are untouched, as a test with real files shows.
- A failed download or a checksum mismatch never stops the helper. A mismatched file is deleted, so Retry downloads it again. A download that finished before a refused swap is kept and verified again on Retry, not fetched again.
- The partial download is now named for its version (`runtime-0.1.9.tar.xz.partial`), and partial files of other versions are removed first. This Mac had a complete 0.1.6 archive under the old name `runtime.tar.xz.partial`. Resuming the 0.1.9 download onto it would have produced a checksum mismatch on the first try.
- While the runtime is swapped, a sidebar refresh or the speech model list does not contact the helper, since that would start the old helper again. After a setup or update run, the speech model list is refreshed, so the new helper's models appear without reopening the sidebar.
- During an update the disk figure is the runtime archive, not the first-run model download. Otherwise a Mac with little free space would show "Not enough disk space" in the middle of a working update.
- This delivers the TICKET-008 item "fetched and swapped in only while no MKV copy or session is using the old helper", which was marked met but had no code.
- Verification: 89 plugin tests, including an end-to-end run of the real plugin bundle against an installed 0.1.6 helper. It runs start 0.1.6, then download, verify, release lease, shutdown, swap runtime, start 0.1.9, and the test clip on the new helper. Mutation checks: stopping before verifying, ignoring the launch mode, skipping the stale-partial cleanup, hiding the controls for an offered update, the first-run disk figure, and no model refresh each fail a test. `scripts/test` (203 helper tests) and `npm run build` pass.
