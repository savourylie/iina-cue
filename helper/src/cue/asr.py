"""A dedicated speech-to-text engine on MLX, used in front of Gemma when chosen.

Gemma still translates; only the transcript comes from this model. The engine
is part of the source cache key, so its transcripts are never served as
Gemma's. Loaded once per worker, like the aligner.
"""
from __future__ import annotations
from pathlib import Path
from .core import CueError, SOURCE_LANGUAGES

# Qwen3-ASR takes language names; None means detect.
LANGUAGE_NAMES = {"zh": "Chinese", "yue": "Cantonese", "en": "English", "de": "German", "es": "Spanish", "fr": "French",
                  "it": "Italian", "pt": "Portuguese", "ru": "Russian", "ko": "Korean", "ja": "Japanese"}
assert set(LANGUAGE_NAMES) == set(SOURCE_LANGUAGES)

class MlxAsr:
    """Qwen3-ASR, or another mlx_audio speech model, as the transcriber."""
    def __init__(self, path: Path, loader=None):
        self.path = Path(path)
        self.key = f"mlx-asr:{self.path.name}"
        self._loader = loader
        self.model = None

    def load(self) -> None:
        if self.model is not None:
            return
        if self._loader is None:
            from mlx_audio.stt.utils import load_model
            self._loader = lambda path: load_model(str(path))
        try:
            self.model = self._loader(self.path)
        except Exception as exc:
            raise CueError("MODEL_LOAD_FAILED", type(exc).__name__) from exc

    def transcribe(self, audio: Path, source: str = "auto", names=()) -> str:
        if source != "auto" and source not in SOURCE_LANGUAGES:
            raise CueError("INVALID_SETTINGS")
        self.load()
        kwargs = {"language": LANGUAGE_NAMES.get(source)}
        if names:
            # Local context only, never film history (spec §6.5).
            kwargs["system_prompt"] = f"The speakers may mention these names, spell them this way: {', '.join(names)}."
        out = self.model.generate(str(audio), **kwargs)
        text = str(getattr(out, "text", out) or "").strip()
        if not text or len(text) > 10000:
            raise CueError("ASR_FAILED", "empty or excessive output")
        return text
