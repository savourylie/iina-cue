# [TICKET-006] Helper setup API: resumable, verified model download and smoke test

## Status
`done`

## Dependencies
- Requires: #005 ✅

## Description
Models (3,564,002,544 bytes, about 4.2 GB on disk with the compile cache) are currently installed with `scripts/setup-models --accept-download` in Terminal. Once the runtime is installed, the helper must download and verify them itself, on the user's explicit consent in the sidebar. It must survive slow or interrupted connections. The spec reserves `GET /setup` and `POST /setup/actions` for this. It also requires a short-audio smoke test after install, because a successful import does not prove the models work.

## Acceptance Criteria
- [x] `GET /setup` reports installed or missing assets, bytes needed, free disk space, sources, and current download progress.
- [x] `POST /setup/actions` accepts only allow-listed actions: start or resume the model download, cancel, verify, and run the smoke test. It never runs an arbitrary command.
- [x] Downloads use the pinned revisions in `models/manifest.json`. They resume partial files with HTTP Range, retry transient failures with backoff, check SHA-256 or Git blob identity, and only then move files into place.
- [x] Download is refused up front when free disk space is insufficient, with the exact amount needed.
- [x] The smoke test transcribes and aligns a short bundled or synthesized clip, and reports pass or fail with a reason.
- [x] Progress survives a helper restart; the next start resumes rather than restarting from zero.

## References
- `scripts/setup-models` — current consent-first, pinned and verified downloader, which has no resume.
- `models/manifest.json` — assets, revisions, sizes and hashes.
- `IINA_AI_SUBTITLES_SPEC.md` — §4.1 first-run flow; the API table lists `GET /setup` and `POST /setup/actions`.
- `helper/src/cue/service.py` — request routing and client authentication.

## Implementation Notes
- Required constraints: download only after explicit user consent; no Hugging Face login; no model substitution; generation stays offline (`HF_HUB_OFFLINE=1`).
- Both model repositories were verified ungated on 2026-09-24 (`gated=False`).

## As-Built Notes

### 2026-09-25
- `GET /v1/setup` and `POST /v1/setup/actions` are the shipped routes. A download starts only for `start` or `resume`. Partial files use HTTP Range and are moved into place only after SHA-256 or Git blob identity matches. Disk refusal reports the exact remaining byte count. A helper restart reads the partial file and resumes it. Without the pinned weights, smoke writes a synthesized clip and returns a failure reason instead of claiming the models work. The ~4 GB assets were not downloaded.

## Testing
- Unit tests with a local HTTP server: interrupted-then-resumed download, corrupted bytes rejected, disk-space refusal, and retry after a transient 5xx error.
- Manual: start a real download, kill the helper halfway, restart, and confirm it resumes and verifies.
