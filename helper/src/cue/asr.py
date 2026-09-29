"""A dedicated speech-to-text engine on MLX, used in front of Gemma when chosen.

Gemma still translates; only the transcript comes from this model. The engine
is part of the source cache key, so its transcripts are never served as
Gemma's. Loaded once per worker, like the aligner.
"""
from __future__ import annotations
import json
from pathlib import Path
from .core import CueError, SOURCE_LANGUAGES

# Qwen3-ASR takes language names; None means detect.
LANGUAGE_NAMES = {"zh": "Chinese", "yue": "Cantonese", "en": "English", "de": "German", "es": "Spanish", "fr": "French",
                  "it": "Italian", "pt": "Portuguese", "ru": "Russian", "ko": "Korean", "ja": "Japanese"}
assert set(LANGUAGE_NAMES) == set(SOURCE_LANGUAGES)


def model_family(path: Path) -> str:
    """The mlx_audio model_type from config.json; Qwen3-ASR when there is none."""
    try:
        return json.loads((Path(path) / "config.json").read_text()).get("model_type") or "qwen3_asr"
    except (OSError, ValueError):
        return "qwen3_asr"

class MlxAsr:
    """Qwen3-ASR or Whisper through mlx_audio as the transcriber."""
    def __init__(self, path: Path, loader=None, family: str | None = None):
        self.path = Path(path)
        self.key = f"mlx-asr:{self.path.name}"
        self._loader = loader
        self.model = None
        self.family = family or model_family(self.path)

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

    def transcribe(self, audio: Path, source: str = "auto", names=(), previous: str = "") -> str:
        if source != "auto" and source not in SOURCE_LANGUAGES:
            raise CueError("INVALID_SETTINGS")
        self.load()
        # Names are local context only, never film history (spec §6.5).
        if self.family == "whisper":
            # Whisper takes ISO codes (None detects) and a text prompt for vocabulary.
            # Whisper copies its prompt. The tail of what was already heard keeps the output
            # cased, punctuated and continuous across the seam; a names list or a seed sentence
            # would be echoed as words (会話の), so names reach it only through that text and the
            # first window gets no prompt. Timestamps stay on because decoding without them
            # drops punctuation and casing.
            kwargs = {"language": None if source == "auto" else source, "return_timestamps": True, "verbose": False}
            if previous.strip():
                kwargs["initial_prompt"] = previous.strip()[-220:]
        else:
            kwargs = {"language": LANGUAGE_NAMES.get(source)}
            if names:
                kwargs["system_prompt"] = f"The speakers may mention these names, spell them this way: {', '.join(names)}."
        out = self.model.generate(str(audio), **kwargs)
        text = str(getattr(out, "text", out) or "").strip()
        if not text and getattr(out, "segments", None):
            text = " ".join(str(seg.get("text", "")).strip() for seg in out.segments).strip()
        if not text or len(text) > 10000:
            raise CueError("ASR_FAILED", "empty or excessive output")
        return text
