# [TICKET-009] Sidebar "Set up Cue" flow

## Status
`blocked`

## Dependencies
- Requires: #006, #008

## Description
A non-technical user's whole setup happens in the Cue sidebar:
1. It explains what will be downloaded and why.
2. It checks the Mac.
3. The user presses one button.
4. The sidebar shows progress through runtime download, model download and the smoke test.
5. It ends in the normal sidebar.

Failures must say what happened and offer the next step, not a code.

## Acceptance Criteria
- [ ] The first-run sidebar shows a setup card instead of the normal controls. It states the total download size, where files come from, that everything runs locally, and the disk space needed.
- [ ] Setup states render distinctly: unsupported Mac with its reason; ready to download; downloading the runtime; downloading models, with determinate progress, bytes and a resume after interruption; verifying; smoke test; ready; failed with retry.
- [ ] Quitting IINA mid-download and reopening it resumes from the saved progress rather than starting over.
- [ ] Credits and licenses are reachable from the setup card and the preferences page. They name Gemma 4 E2B (Google, Apache 2.0) and Qwen3-ForcedAligner (Qwen team, Apache 2.0; MLX conversion by mlx-community), and link to the bundled `licenses/`.
- [ ] Copy follows `DESIGN.md` and uses the string catalog. The status row, tokens and accessibility rules apply: one polite announcer, no live region that updates on every poll.
- [ ] The preferences page's Terminal setup steps apply only to development builds and no longer appear in the general-user path.

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

## Testing
- Sidebar tests for each setup state and for the announcer.
- Stubbed browser preview at 240 px and 360 px in light and dark.
- Manual run in IINA on a Mac with no runtime or models installed.
