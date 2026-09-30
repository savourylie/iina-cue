# Troubleshooting

- **SETUP_REQUIRED**: run `scripts/setup-models` to see the exact missing weights and download plan. Download only after consent, then run a benchmark before native enablement.
- **HELPER_DISCONNECTED**: verify the absolute `bootstrap` setting, project `.venv`, and `.runtime/helper.log`. Stop/retry AI to rebuild a session. Never print/share `.runtime/connection.json`; it contains a local bearer token.
- **MODEL_LOAD_FAILED**: Gemma, the Qwen aligner or the Whisper hearing model did not load; no CPU or cloud fallback is used. Capture runtime versions and the sanitized error. A successful import alone does not establish a working audio backend.
- **ALIGNMENT_LANGUAGE_UNSUPPORTED**: the selected language has a missing ja/ko tokenizer, or the installed aligner cannot accept it. The bundled Qwen forced aligner cannot time Greek.
- **LANGUAGE_UNCERTAIN**: a short or unclear transcript cannot establish the spoken language. This includes an auto-detected language outside Qwen's eleven-language set: text classification can be wrong when ASR mishears speech, so Cue does not treat a candidate such as Polish as proof of the audio language. Cue retries once with a longer local audio window, then leaves an uncaptioned hole and checks later audio as playback advances. The sidebar Source language control can override auto-detection when you want to test one of the supported languages.
- **ALIGNMENT_FAILED**: invalid/missing/non-monotonic units or overlapping chunk boundaries. No affected range is marked installed. A failed boundary may require clearing that movie's cache after stopping AI; automatic boundary reconciliation is not fully qualified.
- **SUBTITLE_INSTALL_FAILED / USER_SUBTITLE_SELECTION**: the exact external track was not confirmed, or the user changed/disabled it during reload. The plugin will not force `sid` back after asynchronous reload.
- **AUDIO_TRACK_MAPPING_AMBIGUOUS**: selected mpv track cannot be matched uniquely against FFprobe. Never use the mpv ID as the FFmpeg stream index. CLI benchmark `--stream` takes an explicit FFprobe stream index.
- **AUDIO_DELAY_UNSUPPORTED**: preview does not support non-zero audio-delay. It does not rewrite the user's setting or sub-delay.
- **CLIENTS_ACTIVE on shutdown**: stop the active AI session(s), then retry. The command will not kill unrelated clients or arbitrary Python/FFmpeg processes.
- **REMUX_CANCELLED**: the MKV copy was cancelled before saving. Cue stopped FFmpeg and removed its temporary file; the original was not touched.
- **REMUX_ACTIVE / REMUX_FAILED / REMUX_VERIFY_FAILED**: only one remux runs at a time. A failed FFmpeg stream copy or an output that does not preserve copied streams and start near zero is discarded; the original file remains intact. MPEG-TS files can contain `timed_id3` data streams that Matroska cannot store; Cue omits data streams and confirms that choice before remuxing. Other incompatible streams can still fail. If the helper or Mac stops during a remux, a hidden `.cue-remux-*` temporary file can remain in the chosen output folder.
- **OUTPUT_EXISTS during remux or export**: Cue never replaces an existing output. Move or rename the old output before trying again.

If playback remains paused after a failure or after subtitles are ready, press play or use “先繼續播放”. This is intentional conservative pause handling, not a claim of final automatic startup UX.

For reproducible evidence: `scripts/test`, `.venv/bin/python scripts/integration-smoke.py`, and `scripts/benchmark --media <permitted clip> ...`. The integration smoke contains only generated digital silence and cannot prove recognition quality or GPU responsiveness.

## Pinning names with a glossary file

Cue learns how it rendered a name once the film has mentioned it twice and keeps that rendering for the rest of the film; a name mentioned only once needs no pinning, and this keeps one-off mishearings out of the list. To correct or pre-seed renderings, put a JSON file next to the video named after it, for example `A Beautiful Mind (2001).cue-glossary.json` for `A Beautiful Mind (2001).mp4`, or a global `~/Library/Application Support/Cue/glossary.json`:

```json
{"zh-TW": {"Nash": "納許", "Hansen": "漢森", "Governing dynamics": "支配動力學"}}
```

One section per target language (`zh-TW`, `zh-CN`, `en`, `ja`, `ko`). The file next to the video wins over the global file, both win over Cue's built-in table of about 650 common English given names and surnames with Taiwan renderings (`helper/src/cue/data/names-zh-TW.json`), and all three win over what Cue learned. Cue only reads these files. A file that is not valid JSON, has non-string entries, entries longer than 64 characters, or kana in a Chinese or Korean section is ignored and `glossary_invalid` is logged. Editing a file makes Cue translate that film again on the next start; the transcript and alignment are reused. `scripts/cue-helper glossary export --media … --target zh-TW --output …` writes what Cue learned so far in this format, ready to edit. `scripts/cue-helper cache clear --media …` also forgets the learned names.

Long native modal dialogs may suspend IINA JavaScript timers. Expired helper/client leases trigger a new session at the current position. Background inference errors preserve already installed subtitle coverage; one shorter-window retry is attempted for ASR/alignment failures. A second failure is explicit.
