# Cue development

- Keep the user's existing specifications and README edits.
- Local seekable media only; no cloud or Eloquent. Gemma 4 E2B stays the default model; a larger model (Gemma 4 E4B or 12B) runs only when the user explicitly chooses and downloads it in Advanced. Never substitute a model silently.
- One persistent inference subprocess; no model load per chunk/window.
- Source timestamps come from forced alignment. Never invent or distribute times.
- Verify mpv track mapping against FFprobe. Unknown language is a valid state.
- Coverage has holes; prepared and player-acknowledged coverage are different.
- Fence asynchronous results by instance, session, seek epoch and profile.
- Never resume a user pause or reclaim a manually changed subtitle selection.
- Run `scripts/test` and `npm run build`; distinguish unit tests from real inference/IINA evidence.
- No private media discovery, large model download without consent, publishing, or global Python changes.
