# Troubleshooting

- **SETUP_REQUIRED**: run `scripts/setup-models` to see the exact missing weights and download plan. Download only after consent, then run a benchmark before native enablement.
- **HELPER_DISCONNECTED**: verify the absolute `bootstrap` setting, project `.venv`, and `.runtime/helper.log`. Stop/retry AI to rebuild a session. Never print/share `.runtime/connection.json`; it contains a local bearer token.
- **MODEL_LOAD_FAILED**: no CPU/Whisper/cloud fallback is used. Capture runtime versions and the sanitized error. A successful import alone does not establish a working audio backend.
- **LANGUAGE_UNCERTAIN**: choose a source language manually. Short or ambiguous text is not assigned English by default.
- **ALIGNMENT_LANGUAGE_UNSUPPORTED**: unsupported language or missing ja/ko tokenizer. Do not force a different language as a workaround.
- **ALIGNMENT_FAILED**: invalid/missing/non-monotonic units or overlapping chunk boundaries. No affected range is marked installed. A failed boundary may require clearing that movie's cache after stopping AI; automatic boundary reconciliation is not fully qualified.
- **SUBTITLE_INSTALL_FAILED / USER_SUBTITLE_SELECTION**: the exact external track was not confirmed, or the user changed/disabled it during reload. The plugin will not force `sid` back after asynchronous reload.
- **AUDIO_TRACK_MAPPING_AMBIGUOUS**: selected mpv track cannot be matched uniquely against FFprobe. Never use the mpv ID as the FFmpeg stream index. CLI benchmark `--stream` takes an explicit FFprobe stream index.
- **AUDIO_DELAY_UNSUPPORTED**: preview does not support non-zero audio-delay. It does not rewrite the user's setting or sub-delay.
- **CLIENTS_ACTIVE on shutdown**: stop the active AI session(s), then retry. The command will not kill unrelated clients or arbitrary Python/FFmpeg processes.

If playback remains paused after a failure or after subtitles are ready, press play or use “先繼續播放”. This is intentional conservative pause handling, not a claim of final automatic startup UX.

For reproducible evidence: `scripts/test`, `.venv/bin/python scripts/integration-smoke.py`, and `scripts/benchmark --media <permitted clip> ...`. The integration smoke contains only generated digital silence and cannot prove recognition quality or GPU responsiveness.

Long native modal dialogs may suspend IINA JavaScript timers. Expired helper/client leases trigger a new session at the current position. Background inference errors preserve already installed subtitle coverage; one shorter-window retry is attempted for ASR/alignment failures. A second failure is explicit.
