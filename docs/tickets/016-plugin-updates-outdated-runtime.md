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
