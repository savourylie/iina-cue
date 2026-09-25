# Third-party notices

These notices describe components that a built Cue helper runtime redistributes. They are not legal advice and do not claim that shipping the texts satisfies every license obligation.

The IINA plugin archive contains this project's JavaScript, HTML, and manifest. It does not contain the Python runtime, FFmpeg, model weights, or their native libraries. The notes below apply to the helper runtime produced by `scripts/build-runtime`.

## What the runtime carries

`scripts/build-runtime` writes a `licenses/` directory into the runtime:

- `THIRD_PARTY_NOTICES.md` — this file.
- `python/LICENSE.txt` — the CPython license from the standalone interpreter.
- `packages/<distribution>/` — license files for every third-party distribution installed in that runtime. `licenses/index.txt` lists each distribution, its version, and whether the file came from the wheel or from an exact-version override. The build fails when a third-party distribution has no recoverable license file.
- `models/` — license text for the pinned Gemma 4 E2B and Qwen3 ForcedAligner artifacts, and for the Silero VAD model. The Gemma and Qwen weights are not inside the runtime; downloading them remains a separate consent step. The Silero VAD model is inside the runtime as `vad/silero_vad.onnx`.
- `ffmpeg/` — present when the static LGPL FFmpeg build is included. It contains FFmpeg's LGPL-2.1 text, the source URL, the SHA-256, the version, and the configure flags.
- `common/MPL-2.0.txt` — the Mozilla Public License 2.0. The certifi and tqdm wheels incorporate that license by reference; their own files are still copied under `packages/`.

The `iina-cue` distribution is listed as first-party. This repository does not ship a license for Cue itself, and this file does not grant one.

`licenses/index.txt` is the list of distributions actually installed in that build. The names below are the obligations that are easy to miss. They are not a substitute for the index.

## Models

Gemma 4 E2B is `litert-community/gemma-4-E2B-it-litert-lm` at revision `b3ca0d2f076785a8f4b2219ddbd2bdb99954eae1`, pinned in `models/manifest.json`. The model card at that revision declares `license: apache-2.0`. The repository is not gated. That revision does not contain a LICENSE file. `licenses/models/gemma-4-e2b/LICENSE` is the Apache License, Version 2.0, which that declaration names. The older page at https://ai.google.dev/gemma/terms does not describe this artifact.

Qwen3-ForcedAligner-0.6B is the upstream repository `Qwen/Qwen3-ForcedAligner-0.6B`. Its model card declares `license: apache-2.0` and the repository is not gated. Cue does not pin a separate upstream revision. The runtime uses the pinned MLX conversion `mlx-community/Qwen3-ForcedAligner-0.6B-4bit` at revision `2f652af86ae0c73fe189b9429225c908ce4bf020`. That card also declares `license: apache-2.0`, the repository is not gated, and the revision does not contain a LICENSE file. Its README says the weights were converted from the Qwen repository. `licenses/models/qwen3-forced-aligner-0.6b/LICENSE` and `licenses/models/qwen3-forced-aligner-0.6b-4bit/LICENSE` are the Apache License, Version 2.0.

## Silero VAD

The runtime carries `vad/silero_vad.onnx`, 2,327,524 bytes, SHA-256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`. It is the file `silero_vad/data/silero_vad.onnx` from the silero-vad 6.2.3 wheel on PyPI, SHA-256 `7b7f5436cfcb02fae583a05b512ea96467fd449fe54cb49a5e4f06c51a1e43b8`, published by the Silero Team (https://github.com/snakers4/silero-vad). The wheel's license is the MIT License, Copyright (c) 2020-present Silero Team. `licenses/models/silero-vad/LICENSE` is that file, and `licenses/models/silero-vad/SOURCE.txt` records the URL and both hashes. The silero-vad package itself is not installed. It runs through onnxruntime, whose wheel license is copied under `licenses/packages/`.

## FFmpeg

When `scripts/build-ffmpeg` output is present, the runtime includes static `ffmpeg` and `ffprobe`. The build record reports `LGPL version 2.1 or later`, with `--disable-gpl` and `--disable-nonfree`. The build script's current pin is FFmpeg 7.1.1 from `https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz`, SHA-256 `733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1`. That URL, hash, version, license line, and configure line are copied to `licenses/ffmpeg/build-record.txt`. `licenses/ffmpeg/COPYING.LGPLv2.1` is the license text from that source tree. The same build record is also copied to `bin/ffmpeg-build-record.txt`.

The binaries are statically linked. They do not use a shared FFmpeg library. LGPL-2.1 section 6 says a distributor of a statically linked work must provide the library source and enough material to relink the application with a modified library, or use a suitable shared library. This runtime ships the license text, the exact source URL and hash, and the configure flags. It does not ship the FFmpeg source tree or FFmpeg object files. This paragraph records that fact. It does not say the record meets the license.

A runtime built before that FFmpeg directory exists does not contain these binaries or `licenses/ffmpeg/`. That tree is not the distributable runtime described here. The Python runtime build still succeeds without it.

## soynlp

`soynlp` 0.0.493 is installed because the Qwen aligner's Korean path imports it. The wheel's metadata `License` field is `UNKNOWN`. Its trove classifier says `GNU General Public License v3 (GPLv3)`. The upstream LICENSE file, added on GitHub before the 0.0.493 upload and not included in the wheel or sdist, is the GNU Lesser General Public License, version 3, with a copyright line for lovit. The build copies that file to `licenses/packages/soynlp/LICENSE`.

The LGPL-3.0 text says a combined work is accompanied by both that license and the GNU GPL. `licenses/packages/soynlp/COPYING` is GPL version 3. The Python sources of soynlp are installed in site-packages. This note does not say that shipping those sources and these two texts meets the LGPL. A different soynlp version with no license file fails the build until that override is reviewed.

## Other packages named in the audit

certifi's wheel declares MPL-2.0. tqdm's wheel declares `MPL-2.0 AND MIT`. tqdm's license file says the files attributed to Casper da Costa-Luis are MPL-2.0 and other parts are MIT. Those wheel files are copied under `licenses/packages/`. They point at MPL-2.0 instead of including the full license; `licenses/common/MPL-2.0.txt` is that text.

These exact versions declare Apache-2.0, or carry an Apache classifier, but ship no license file: Cython 3.3.0, dyNET38 2.2, flatbuffers 25.12.19 (required by onnxruntime), litert-lm-api 0.17.1, sentencepiece 0.2.2, and tokenizers 0.23.2. The build copies the Apache License, Version 2.0, for those versions only. Another version with no license file fails the build.

## Development tools

TypeScript, esbuild, tsx, and pytest are development dependencies. They are not installed into the helper runtime. IINA is not bundled in the runtime.

dora was a local design reference. None of its source or environment is included.

The pinned model identities are in `models/manifest.json`. This notice does not grant rights to a user's movie.
