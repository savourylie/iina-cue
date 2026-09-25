# [TICKET-009] Sidebar "Set up Cue" flow

## Status
`done`

## Dependencies
- Requires: #006 ✅, #008 ✅

## Description
A non-technical user's whole setup happens in the Cue sidebar:
1. It explains what will be downloaded and why.
2. It checks the Mac.
3. The user presses one button.
4. The sidebar shows progress through runtime download, model download and the smoke test.
5. It ends in the normal sidebar.

Failures must say what happened and offer the next step, not a code.

## Acceptance Criteria
- [x] The first-run sidebar shows a setup card instead of the normal controls. It states the total download size, where files come from, that everything runs locally, and the disk space needed.
- [x] Setup states render distinctly: unsupported Mac with its reason; ready to download; downloading the runtime; downloading models, with determinate progress, bytes and a resume after interruption; verifying; smoke test; ready; failed with retry.
- [x] Quitting IINA mid-download and reopening it resumes from the saved progress rather than starting over.
- [x] Credits and licenses are reachable from the setup card and the preferences page. They name Gemma 4 E2B (Google, Apache 2.0) and Qwen3-ForcedAligner (Qwen team, Apache 2.0; MLX conversion by mlx-community), and link to the bundled `licenses/`.
- [x] Copy follows `DESIGN.md` and uses the string catalog. The status row, tokens and accessibility rules apply: one polite announcer, no live region that updates on every poll.
- [x] The preferences page's Terminal setup steps apply only to development builds and no longer appear in the general-user path.

## Design Reference
- `DESIGN.md` — "The Quiet Inspector": the status row, the "Tint, Not Paint" rule, native controls, and help shown only when it applies.
- `PRODUCT.md` — "Tell the truth about state"; local and private by construction.

## Visual Reference
The setup card lives in the same single column as the sidebar, at 240 px and 360 px, in light and dark. A single primary action appears per state. Progress is a native `<progress>` element with bytes and percent in tabular numerals.

## References
- `plugin/sidebar.html`, `plugin/src/strings.ts`, `plugin/src/control.ts` — the status row and string catalog patterns to follow.
- `plugin/preferences.html` — current setup steps.

## Implementation Notes
- Required constraints: never start a download without the user pressing the button; never claim readiness before the smoke test passes.
- Suggested approach: run `/impeccable critique` on the setup card before and after, as for the sidebar.

## As-Built Notes

### 2026-09-25
- The setup card replaces the normal controls until the phase is `done`, which requires the smoke test to have passed. A repeated poll of the same phase does not write the polite announcer. The progress element is a native `<progress>` and is not a live region. Saved byte counts render as the resume point. Terminal steps on the preferences page are in a hidden development block. IINA itself was not driven.

### 2026-09-25 (wiring)
- The first PR had the card but nothing drove it: `main.ts` never called the helper's setup API. `setup-controller.ts` now drives the whole flow from the sidebar's `ready` and `start-setup` messages.
- Preflight reads this Mac with `/usr/sbin/sysctl` (`hw.optional.arm64`, `hw.memsize`), `/usr/bin/sw_vers` and `/bin/df -Pk ~/Library`, and IINA's version with `iina.core.getVersion()`. A fact that cannot be read is left unknown and is not checked. The first draft passed fixed values for all of these. After the helper answers, free space and missing bytes come from the helper.
- The runtime is downloaded only while the helper cannot answer. Retry after a stopped model download sends `resume` and does not download the runtime again. A second press while setup runs is ignored.
- The controller polls `GET /v1/setup` every second while the helper reports `downloading` or `smoking`. The smoke test starts only after `files_ready`. The first draft sent `smoke` right after `start` and always failed.
- The IINA bundle imports no `node:` module. The Node-only unpack helper moved to `install-archive.ts`, which tests use.
- IINA itself was still not driven. This Mac already has a working Cue install, and the clean-Mac run belongs to TICKET-012.

## Testing
- Sidebar tests for each setup state and for the announcer.
- Stubbed browser preview at 240 px and 360 px in light and dark.
- Manual run in IINA on a Mac with no runtime or models installed.
