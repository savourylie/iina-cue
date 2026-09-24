# [TICKET-003] Ship license notices with the runtime and update THIRD_PARTY_NOTICES

## Status
`pending`

## Dependencies
- Requires: #001 ✅, #002 ✅

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

## As-Built Notes

### 2026-09-24
- `scripts/collect_licenses.py` runs from `scripts/build-runtime` after the locked packages are installed. It writes `licenses/` into the runtime before the path scan, and the archive includes that directory. Copying these texts is not a legal opinion.
- A third-party distribution must have a non-empty license file in its wheel, or an exact-version override. Otherwise the build fails. `iina-cue` is recorded as first-party: this repository ships no project license, and `licenses/packages/iina-cue/FIRST_PARTY.txt` does not grant one.
- Wheels with no license file, pinned to the locked version: Cython 3.3.0, dyNET38 2.2, litert-lm-api 0.17.1, sentencepiece 0.2.2, and tokenizers 0.23.2. Their metadata declares Apache-2.0, so the build copies that license. `soynlp` 0.0.493 is different: the wheel and sdist omit a license file, metadata says `UNKNOWN`, and the classifier says GPLv3. The GitHub LICENSE added before the 0.0.493 upload is LGPL-3.0. The build copies that file plus GPL-3.0, because the LGPL text says to accompany the library with the GPL. A version bump with no wheel license fails until the override is reviewed.
- When `dist/ffmpeg-*` is present, `licenses/ffmpeg/` gets `COPYING.LGPLv2.1` and `build-record.txt` (source URL, SHA-256, version, configure flags). A GPL or nonfree configure line fails the build. The binaries stay a static LGPL-2.1-or-later build and the runtime still does not include FFmpeg's source tree or object files. A Python-only tree still builds when that directory is absent; the notices say it is not the distributable runtime.
- The pinned Gemma and Qwen model cards declare `apache-2.0`, are not gated, and do not contain a LICENSE file. `licenses/models/` carries the Apache-2.0 text and a source note for each. `THIRD_PARTY_NOTICES.md` says the older Gemma terms page does not describe these artifacts. `docs/install.md` and `scripts/setup-models` now point at those notices instead of that page.
- Checked on this Mac: `helper/tests/test_collect_licenses.py` (including a test package whose license file was removed), `scripts/test` (91 pytest tests, plugin tests, and `npm run build`), and `scripts/build-runtime`. The built `dist/runtime-0.1.5` index matched all 56 distributions from that runtime's `importlib.metadata` (49 wheel, 6 override, 1 first-party). `licenses/` is 712K. The archive is 273,726,664 bytes and contains the FFmpeg license, the soynlp license, the Gemma license, and Python's license. No notarized install was run.
