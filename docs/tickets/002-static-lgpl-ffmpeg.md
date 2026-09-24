# [TICKET-002] Build a static LGPL FFmpeg for the runtime

## Status
`pending`

## Dependencies
- Requires: None

## Description
Cue currently runs the machine's FFmpeg, which on the development Mac is Homebrew's GPL build with 37 dynamic libraries. A distributable runtime needs its own FFmpeg and FFprobe: static, LGPL-only, and depending on nothing outside macOS.

The feasibility pass built FFmpeg 7.1.1 from the ffmpeg.org source tarball in 28 seconds, with `--disable-autodetect --disable-network --disable-doc --disable-ffplay --disable-debug --enable-static --disable-shared --enable-audiotoolbox`. The result reported "LGPL version 2.1 or later". Both binaries together were 41 MB, or 13 MB as `tar.xz`. Cue's `extract`, `probe` and `remux` succeeded on H.264, HEVC, VP9 and ProRes with AAC, AC3, E-AC3, Opus, FLAC, MP3 and PCM, including multiple audio tracks. The DTS and TrueHD decoders are present.

## Acceptance Criteria
- [ ] A script downloads a pinned FFmpeg source release, checks its SHA-256, and builds static `ffmpeg` and `ffprobe` for arm64.
- [ ] `configure` reports an LGPL license; `otool -L` shows only system libraries.
- [ ] The exact source URL, hash and configure flags are recorded for license compliance.
- [ ] Cue's media and remux tests pass when `cue.media.binary` resolves to these binaries.

## References
- `helper/src/cue/media.py` — `binary()`, `probe()` and `extract()`.
- `helper/src/cue/remux.py` — stream copy and verification.
- `helper/tests/test_media.py` — existing media and remux coverage. Its fixture currently encodes with libx264, which the LGPL build lacks.

## Implementation Notes
- Required constraints: no GPL or nonfree components. Never bundle the Homebrew build.
- Suggested approach: keep generating test fixtures with a separate encoder, or build fixtures from lavfi sources the LGPL build can encode. Run Cue's code under test with the LGPL binaries.

## Testing
- Build, then run the media and remux tests with the LGPL binaries.
- `ffmpeg -decoders` must list aac, ac3, eac3, dca, truehd, opus, flac and mp3.

## As-Built Notes

### 2026-09-24
- `scripts/build-ffmpeg` downloads FFmpeg 7.1.1 from `https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz` and checks SHA-256 `733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1`. ffmpeg.org does not publish a `.sha256` file; the pin is the hash of that tarball. The script is arm64-only and never copies Homebrew.
- Configure flags, also written to `dist/ffmpeg-7.1.1/build-record.txt`: `--prefix=/cue-ffmpeg --disable-autodetect --disable-network --disable-doc --disable-ffplay --disable-debug --enable-static --disable-shared --enable-audiotoolbox --disable-gpl --disable-nonfree`. `config.h` reports `LGPL version 2.1 or later`, with `CONFIG_GPL` and `CONFIG_NONFREE` set to 0. `--prefix=/cue-ffmpeg` is not created; `make install` uses `DESTDIR`, so the binaries do not embed this machine's temporary directory. `otool -L` shows only AudioToolbox, CoreAudio, CoreFoundation, CoreVideo, CoreMedia, and `libSystem`. Each binary is about 20 MB.
- The same script copies `ffmpeg`, `ffprobe`, and the build record into `dist/runtime-<HELPER_VERSION>/bin/` when that runtime already exists, then refreshes its archive. `scripts/build-runtime` performs the same copy after its path scan, and still succeeds when FFmpeg has not been built. `licenses/` and `THIRD_PARTY_NOTICES.md` stay with #003. The LGPL text is only at `dist/ffmpeg-7.1.1/COPYING.LGPLv2.1`.
- `binary()` uses `CUE_FFMPEG_BIN_DIR` when it is set, and does not fall back to Homebrew. Unset, the old search order remains. Installed-mode lookup is still #005. `doctor.py` still reports `/opt/homebrew/bin/ffmpeg`.
- Media fixtures in `helper/tests/test_media.py` encode with `mpeg4 -bf 0` because this build has no libx264. `scripts/integration-smoke.py` and `scripts/make-speech-fixtures.py` still use libx264. No minimum macOS deployment target was chosen.
