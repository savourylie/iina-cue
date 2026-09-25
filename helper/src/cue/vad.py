"""Silero VAD: does an audio window contain speech at all?

VAD only decides whether a window reaches ASR. It never produces or adjusts a
cue time; source times come from forced alignment alone (spec §6.1).

The model is the official silero_vad.onnx from the PyPI silero-vad 6.2.3 wheel
(MIT, Silero Team). That package requires PyTorch, so only its model file is
used, through onnxruntime on the CPU. The streaming code follows the wheel's
OnnxWrapper, and the segment rule follows get_speech_timestamps_from_probs.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from .core import CueError

VAD_WHEEL_URL = ("https://files.pythonhosted.org/packages/84/ef/9099037ed6f180ea33220178df4107112c0ce2bf5fb4d6f6ab19db2844ed/"
                 "silero_vad-6.2.3-py3-none-any.whl")
VAD_WHEEL_SHA256 = "7b7f5436cfcb02fae583a05b512ea96467fd449fe54cb49a5e4f06c51a1e43b8"
VAD_MODEL_MEMBER = "silero_vad/data/silero_vad.onnx"
VAD_MODEL_SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
VAD_LICENSE_MEMBER = "silero_vad-6.2.3.dist-info/licenses/LICENSE"
VAD_LICENSE_SHA256 = "2e63e9a38b6e8fc0c7bc37ce174caca1862870856c6daf5697cfb785e925520b"

RATE = 16000
FRAME = 512      # 32 ms at 16 kHz, the only frame size the model accepts
CONTEXT = 64     # samples of the previous frame the model sees before each frame
# Silero's defaults. A window counts as speech when any segment passes this rule.
THRESHOLD = 0.5
NEG_THRESHOLD = 0.35
MIN_SPEECH_MS = 250
MIN_SILENCE_MS = 100
# Part of the cache key: a different model or rule can change which windows reach ASR.
VAD_ID = f"silero-vad-6.2.3:{VAD_MODEL_SHA256[:12]}:{THRESHOLD}/{NEG_THRESHOLD}/{MIN_SPEECH_MS}/{MIN_SILENCE_MS}"


def speech_segments(probs: list[float], total_samples: int | None = None) -> list[tuple[int, int]]:
    """Speech segments in samples, by the rule of silero-vad's get_speech_timestamps_from_probs
    with its defaults. Maximum-duration splitting and edge padding are left out: they move
    segment edges but never decide whether a segment exists."""
    min_speech = RATE * MIN_SPEECH_MS / 1000
    min_silence = RATE * MIN_SILENCE_MS / 1000
    total = len(probs) * FRAME if total_samples is None else total_samples
    segments: list[tuple[int, int]] = []
    triggered, start, temp_end = False, 0, 0
    for index, prob in enumerate(probs):
        sample = FRAME * index
        if prob >= THRESHOLD and temp_end:
            temp_end = 0
        if prob >= THRESHOLD and not triggered:
            triggered, start = True, sample
            continue
        if prob < NEG_THRESHOLD and triggered:
            if not temp_end:
                temp_end = sample
            if sample - temp_end < min_silence:
                continue
            if temp_end - start > min_speech:
                segments.append((start, temp_end))
            triggered, temp_end = False, 0
    if triggered and total - start > min_speech:
        segments.append((start, total))
    return segments


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SileroVad:
    """One onnxruntime session for the life of the inference worker."""

    def __init__(self, path: Path):
        if path.is_symlink() or not path.is_file():
            raise CueError("SETUP_REQUIRED", "voice activity model is missing")
        if file_sha256(path) != VAD_MODEL_SHA256:
            raise CueError("SETUP_REQUIRED", "voice activity model does not match its checksum")
        try:
            import onnxruntime
            options = onnxruntime.SessionOptions()
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            self.session = onnxruntime.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise CueError("MODEL_LOAD_FAILED", f"voice activity model: {type(exc).__name__}") from exc

    def probabilities(self, audio) -> list[float]:
        """Per-frame speech probability for mono float32 audio at 16 kHz."""
        import numpy as np
        samples = np.ascontiguousarray(audio, dtype=np.float32).reshape(-1)
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros(CONTEXT, dtype=np.float32)
        rate = np.array(RATE, dtype=np.int64)
        probs: list[float] = []
        for offset in range(0, samples.size, FRAME):
            frame = np.zeros(FRAME, dtype=np.float32)
            chunk = samples[offset:offset + FRAME]
            frame[:chunk.size] = chunk
            x = np.concatenate((context, frame))[None, :]
            out, state = self.session.run(None, {"input": x, "state": state, "sr": rate})
            probs.append(float(out.reshape(-1)[0]))
            context = x[0, -CONTEXT:]
        return probs

    def has_speech(self, audio) -> tuple[bool, dict]:
        probs = self.probabilities(audio)
        segments = speech_segments(probs, len(audio))
        return bool(segments), {"vad_max_prob": round(max(probs, default=0.0), 4),
                                "vad_speech_ms": round(sum(b - a for a, b in segments) * 1000 / RATE)}
