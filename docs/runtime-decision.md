# Runtime decision — verified local vertical slice

The selected runtime is **LiteRT-LM 0.17.1 GPU language + CPU audio, Gemma 4 E2B full multimodal artifact, MLX-Audio 0.4.8 Qwen3 ForcedAligner 0.6B 4bit**. Real audio, translation, four-language alignment fixtures and two complete 3-minute runs succeeded on this M3 Max. See `feasibility.md` for measured limits.

The GPU-only artifact at the same revision failed with `TF_LITE_AUDIO_ENCODER_HW not found`. It was replaced by the full 2,588,147,712-byte artifact; no larger model or alternate backend was substituted. Compilation cache is created before Engine initialization.

## Pinning and security

- Exact repositories, revisions, filenames, byte counts and large-weight SHA-256 hashes are in `models/manifest.json`; small Git assets are verified by their pinned Git blob identity. `uv.lock` and `package-lock.json` fix dependencies.
- Generation sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; it loads only paths under the explicitly configured model directory. Installation/download is a separate opt-in command.
- MLX-Audio 0.4.8's reviewed `qwen3_forced_aligner.py` post-load hook internally supplies `trust_remote_code=True` to AutoTokenizer. Cue first rejects any `auto_map` in the local JSON assets or Python files in the aligner directory. No arbitrary model code is provided or permitted; no remote code permission is assumed. This guard and artifact review must remain if the dependency is upgraded.
- Qwen's Japanese path imports `nagisa`; Korean imports `soynlp`. They are installed and locked; all four generated-language fixtures passed alignment. Natural dialogue quality remains unqualified.
- The GPU backend may fail rather than silently switching to CPU. E2B conversations are per-call and bounded; the engine stays loaded between jobs.

## Performance decisions

One model-owning subprocess services all windows, with one bounded job in flight. Windows share neither mutable player state nor subtitle artifacts. First window 10 s, subsequent 16 s, 1 s context each side; a trailing 1 s draft and any straddling word are not marked complete. A seek fences publication but lets a bounded running job finish into reusable cache. Translation accepts up to 8 cues per JSON request; short request aliases restore stable IDs after validation and reuse source cue timings. High water stops new jobs, with at most one-window overshoot. Only actual benchmark results can establish whether these decisions outperform dora.

## Primary references checked

- [LiteRT Python API](https://developers.google.com/edge/litert-lm/python)
- [Gemma LiteRT artifact](https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/tree/b3ca0d2f076785a8f4b2219ddbd2bdb99954eae1)
- [Qwen MLX artifact](https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-4bit/tree/2f652af86ae0c73fe189b9429225c908ce4bf020)
- [IINA 1.4.4 manifest parser](https://github.com/iina/iina/blob/v1.4.4/iina/JavascriptPlugin.swift)
- [IINA 1.4.4 HTTP implementation](https://github.com/iina/iina/blob/v1.4.4/iina/JavascriptAPIHttp.swift)
- [IINA 1.4.4 global messaging](https://github.com/iina/iina/blob/v1.4.4/iina/JavascriptAPIGlobal.swift)

The installed release uses `globalEntry`; global messages return the sender's player label. That API was inspected during the initial broker prototype; the final transport is described below. IINA's HTTP wrapper sends dictionary form data, so Cue uses a JSON `payload` field in a form envelope.

## Player transport

Each native player now holds its own authenticated helper client lease and calls loopback directly. The bootstrap file lock and supervisor still guarantee one helper/worker across windows. `globalEntry` remains a valid manifest entry but no longer relays mutable replies across two JavaScript contexts. Webviews receive only display state and button actions, never credentials. The service enforces client ownership.
