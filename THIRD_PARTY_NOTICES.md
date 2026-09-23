# Third-party sources

The IINA plugin archive contains this project's JavaScript/HTML and manifest, not model weights, Python, FFmpeg, IINA or their native libraries. Development dependencies are installed separately in the project. Redistributing a standalone helper/runtime requires a separate license and native dependency audit; that release audit is pending.

| Component | Source / terms |
|---|---|
| IINA and plugin definitions | https://github.com/iina/iina ; https://github.com/iina/iina-plugin-definition |
| LiteRT-LM | https://github.com/google-ai-edge/LiteRT-LM |
| Gemma 4 E2B | https://ai.google.dev/gemma/terms ; https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm |
| Qwen3 ForcedAligner / MLX conversion | https://github.com/QwenLM/Qwen3-ASR ; https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-4bit |
| MLX / MLX-Audio | https://github.com/ml-explore/mlx ; https://github.com/Blaizzy/mlx-audio |
| nagisa / soynlp | https://github.com/taishi-i/nagisa ; https://github.com/lovit/soynlp |
| Lingua | https://github.com/pemistahl/lingua-py |
| FFmpeg | https://ffmpeg.org/legal.html ; uses the machine's installed build, not bundled |
| Transformers / PyTorch | https://github.com/huggingface/transformers ; https://github.com/pytorch/pytorch ; existing dora environment used only for the diagnostic |
| NumPy / SoundFile | https://numpy.org ; https://github.com/bastibe/python-soundfile |
| TypeScript / esbuild / tsx / pytest | upstream projects and exact dependency versions in lockfiles |

The exact LiteRT and Qwen revision/artifact identities are in `models/manifest.json`. Gemma's model terms are distinct from runtime/source licenses. A README or project source license does not grant rights to redistribute every dependency or the user's movie.

dora was inspected as a local design reference; no source files, private movie material or its environment were modified/copied into this repository. The speech fixture's sentence was authored for this test and synthesized locally by macOS; it is a synthetic diagnostic, not held-out human speech.
