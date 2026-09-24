# [TICKET-001] Build a relocatable helper runtime

## Status
`done`

## Dependencies
- Requires: None

## Description
General users must not install Python, uv, Node or Homebrew. Build a self-contained helper runtime directory that holds a standalone CPython 3.12 with the exact locked dependencies and Cue's helper package, and runs from any path.

The 2026-09-24 feasibility pass already proved the approach. A copy of uv's standalone CPython 3.12.11, with `uv export --frozen --no-dev` requirements installed into it, was moved to a path containing spaces. From there it loaded MLX (Metal) and LiteRT in a clean environment and produced subtitles identical to the project `.venv`. The runtime was 928 MB, or 239 MB as `tar.xz`.

## Acceptance Criteria
- [x] One command builds the runtime from `uv.lock` into a versioned output directory without touching the project `.venv` or global Python.
- [x] The runtime contains standalone CPython 3.12, the locked non-dev dependencies and `helper/src/cue`, and records its own version.
- [x] Package `tests/` directories and other non-runtime payloads are removed. This avoids the notary warnings seen for joblib and scipy test archives.
- [x] `.pyc` files are compiled at build time, so first launch writes nothing into the runtime and prints no SyntaxWarnings.
- [x] Moved to a different path containing spaces, the runtime starts `cue.cli doctor` and a benchmark under `env -i`, with no reference to the build machine's paths.
- [x] The output reports the uncompressed and compressed sizes.

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

## As-Built Notes

### 2026-09-24
- `scripts/build-runtime` copies the uv-managed CPython (`uv python find 3.12 --no-project --managed-python`). Inside this checkout, `uv python find 3.12` returns the editable `.venv`, which is not relocatable. The project `.venv` and the managed prefix are left unchanged. Wheel downloads use `.cache/uv` and `UV_LINK_MODE=copy`.
- Dependencies come from `uv export --frozen --no-dev --no-emit-project`. The default export starts with `-e .`, so the project is installed afterwards with `--no-deps` as a normal wheel. This uv rejects `--only-binary :all`; the script uses `--no-build` for the locked requirements. Environment markers are applied, so Windows-only `colorama` is not installed on macOS.
- The output is `dist/runtime-<HELPER_VERSION>/` plus `dist/runtime-<HELPER_VERSION>.tar.xz`. `VERSION` is `HELPER_VERSION` from `bootstrap.py` (0.1.5), not the 0.1.0 package version. `lingua` is not slimmed, so detection stays `from_all_languages()`.
- `_sysconfigdata` resolves its prefix from `sys.base_prefix`. `libpython3.12.dylib`'s install name is rewritten to `@loader_path/libpython3.12.dylib` and ad-hoc signed so the file no longer names the uv prefix; #004 replaces that signature. Bytecode paths are relative to the runtime root. Shebangs use the standalone Python relative launcher. Site-packages `test` and `tests` directories are removed. `licenses/` and FFmpeg are left to #003 and #002.
- `bootstrap.py` is unchanged. Without `CUE_HOME`, benchmark scratch would be written under `python/lib` because `PROJECT` is derived from the installed package. Installed-mode paths remain #005. Verification sets `CUE_HOME` outside the tree.
- Built size on this machine: `du -sh` 1.0G (`du -sk` 1051876), tar.xz 256M (259654916 bytes). That is larger than the 928 MB / 239 MB feasibility note; `lingua` is still 293 MB. The benchmark on this Mac still uses Homebrew FFmpeg.
