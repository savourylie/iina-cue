# [TICKET-012] TEST: Checkpoint 1 — Clean install on a SIP-enabled Mac

## Status
`blocked`

## Dependencies
- Requires: #004 ✅, #008, #009, #010, #011

## Description
This gate proves the whole path the way a real user meets it, which no single ticket covers:
- the plugin is downloaded through a browser, so it carries a quarantine flag;
- it is installed by IINA;
- the notarized runtime and the models are downloaded inside IINA;
- captions play;
- throughout, a Mac that has never had Homebrew, Python, Node or the project checkout is used, with SIP enabled.

Publishing Cue as ready for general users waits on this gate.

## Acceptance Criteria
- [ ] On the SIP-enabled second Mac, with no developer tools used, installation reaches working captions by following only the install guide.
- [ ] No macOS "Not Opened", "cannot be verified" or malware dialog appears at any point.
- [ ] Both install routes work: double-clicking a browser-downloaded `.iinaplgz`, and IINA's "Install from GitHub".
- [ ] An interrupted runtime download and an interrupted model download both resume correctly.
- [ ] Removing Cue by following the guide leaves no helper process running, and removes all data in the documented locations.

## Testing
- Manual run by the user on the second Mac. Record the macOS and IINA versions, the timings, screenshots of every dialog, and any confusion.
- Record the results in `docs/acceptance.md`.

## Implementation Notes
- The 2026-09-24 probe on this Mac showed that quarantined unsigned binaries are blocked, while the same binary without quarantine runs. This gate confirms that the notarized runtime also runs.
