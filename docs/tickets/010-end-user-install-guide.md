# [TICKET-010] End-user install guide and README

## Status
`blocked`

## Dependencies
- Requires: #009

## Description
The public README and install docs currently describe a developer workflow. A non-technical user needs a short guide:
- what Cue needs: an Apple Silicon Mac, macOS 14 or later, IINA 1.4 or later, free disk space and RAM;
- how to install: double-click the `.iinaplgz`, or use IINA's "Install from GitHub";
- what the scary IINA permission dialog means;
- what the first-run download is.

## Acceptance Criteria
- [ ] The guide explains both install routes, step by step, with no Terminal commands.
- [ ] It explains IINA's red permission warning ("can execute other programs or applications that can harm your computer"): why Cue needs file-system access, that it connects only to the release host and 127.0.0.1, and that the runtime is notarized by Apple.
- [ ] It states system requirements, including the RAM threshold from #011, and the approximate download size and time.
- [ ] Troubleshooting covers an unsupported Mac, low disk space, an interrupted download and how to remove Cue completely.
- [ ] The developer workflow stays documented separately, and existing user-written README content is preserved.

## References
- `README.md`, `docs/install.md`, `docs/troubleshooting.md` — current docs; keep the author's edits.

## Implementation Notes
- Required constraints: keep the user's existing specifications and README edits (AGENTS.md).

## Testing
- Someone unfamiliar with the project follows the guide on the #012 test Mac without help. Note every point where they hesitate.
