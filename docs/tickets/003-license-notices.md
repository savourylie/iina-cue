# [TICKET-003] Ship license notices with the runtime and update THIRD_PARTY_NOTICES

## Status
`blocked`

## Dependencies
- Requires: #001, #002

## Description
Distributing the runtime redistributes every Python package and FFmpeg, so their licenses must travel with it. The project notices are also out of date: they point to the old Gemma terms and say FFmpeg is not bundled.

Findings from 2026-09-24:
- **Models:** Gemma 4 moved to Apache 2.0 in April 2026. The Qwen3-ForcedAligner-0.6B upstream and the mlx-community 4-bit conversion are Apache 2.0. Neither Hugging Face repo is gated.
- **Runtime packages:** almost all bundled packages are MIT, BSD, Apache or PSF. certifi and tqdm are MPL-2.0. `soynlp` is LGPL-3.0; its package metadata says "UNKNOWN", but its LICENSE file says LGPL-3.0.
- **FFmpeg:** the self-built static FFmpeg is LGPL-2.1 or later.

## Acceptance Criteria
- [ ] The runtime build produces a `licenses/` folder with every bundled package's license file, FFmpeg's license, source reference and build configuration, Python's license, and the model licenses.
- [ ] The build fails when a bundled package has no recoverable license file, so a new dependency cannot ship without one.
- [ ] `THIRD_PARTY_NOTICES.md` describes the bundled runtime, the Apache 2.0 terms for Gemma 4 and the Qwen aligner, and LGPL obligations for FFmpeg and soynlp.

## References
- `THIRD_PARTY_NOTICES.md` — current, outdated notices.
- `models/manifest.json` — pinned model repositories and revisions.
- `docs/runtime-decision.md` — runtime and model choices.

## Implementation Notes
- Required constraints: do not claim legal compliance beyond what the notices provide; this is not legal advice.
- Suggested approach: read `*.dist-info/licenses/*` and `LICENSE*` from site-packages. Keep an explicit override table for packages with missing metadata, such as soynlp.

## Testing
- Build the runtime and check that `licenses/` has an entry for every distribution listed by `importlib.metadata`.
- Remove a license file from a test package and confirm the build fails.
