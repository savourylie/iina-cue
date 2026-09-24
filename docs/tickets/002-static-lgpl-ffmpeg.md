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
