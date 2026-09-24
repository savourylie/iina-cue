# [TICKET-001] Build a relocatable helper runtime

## Status
`pending`

## Dependencies
- Requires: None

## Description
General users must not install Python, uv, Node or Homebrew. Build a self-contained helper runtime directory that holds a standalone CPython 3.12 with the exact locked dependencies and Cue's helper package, and runs from any path.

The 2026-09-24 feasibility pass already proved the approach. A copy of uv's standalone CPython 3.12.11, with `uv export --frozen --no-dev` requirements installed into it, was moved to a path containing spaces. From there it loaded MLX (Metal) and LiteRT in a clean environment and produced subtitles identical to the project `.venv`. The runtime was 928 MB, or 239 MB as `tar.xz`.

## Acceptance Criteria
- [ ] One command builds the runtime from `uv.lock` into a versioned output directory without touching the project `.venv` or global Python.
- [ ] The runtime contains standalone CPython 3.12, the locked non-dev dependencies and `helper/src/cue`, and records its own version.
- [ ] Package `tests/` directories and other non-runtime payloads are removed. This avoids the notary warnings seen for joblib and scipy test archives.
- [ ] `.pyc` files are compiled at build time, so first launch writes nothing into the runtime and prints no SyntaxWarnings.
- [ ] Moved to a different path containing spaces, the runtime starts `cue.cli doctor` and a benchmark under `env -i`, with no reference to the build machine's paths.
- [ ] The output reports the uncompressed and compressed sizes.

## References
- `pyproject.toml`, `uv.lock` — the dependency set to reproduce exactly.
- `scripts/setup-dev` — how the development environment is built today.
- `helper/src/cue/bootstrap.py` — `PROJECT`, `runtime_root()` and `models_root()`, which assume the project checkout.

## Implementation Notes
- Required constraints: no global Python changes; keep the uv cache inside the project (`.cache/uv`); Apple Silicon (arm64) only; the runtime must not need network access at run time.
- Suggested approach: a new `scripts/build-runtime`. Copy `uv python find 3.12`'s install, run `uv pip install --python <runtime python> -r <exported requirements>`, then strip and precompile.
- Optional slimming: `lingua` is 293 MB on disk. Restricting it to the languages Cue uses may shrink the download; measure before and after.

## Testing
- Build, move the output to `/tmp/Cue Runtime Test/runtime`, then run `env -i HOME=$HOME PATH=/usr/bin:/bin <runtime>/python/bin/python3.12 -m cue.cli benchmark ...` against a synthetic `say`-generated clip with `CUE_MODELS` pointing to existing models.
- Compare the rendered cues with the same run from the project `.venv`; they must be identical.
