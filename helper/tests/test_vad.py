import subprocess
import numpy as np
import pytest
import soundfile as sf
from cue.bootstrap import PROJECT
from cue.core import CueError
from cue.media import Media
from cue.service import Supervisor
from cue.vad import FRAME, RATE, SileroVad, speech_segments

MODEL = PROJECT / ".runtime" / "vad" / "silero_vad.onnx"
needs_model = pytest.mark.skipif(not MODEL.is_file(), reason="run scripts/fetch-vad .runtime/vad to test with the Silero model")

def frames(ms):
    return round(ms * RATE / 1000 / FRAME)

def test_no_probability_reaching_the_threshold_is_no_speech():
    assert speech_segments([0.1, 0.49, 0.3] * 50) == []

def test_speech_must_last_longer_than_250_ms():
    short = [0.0] * 5 + [0.9] * frames(224) + [0.0] * 10
    long = [0.0] * 5 + [0.9] * frames(320) + [0.0] * 10
    assert speech_segments(short) == []
    assert speech_segments(long) == [(5 * FRAME, (5 + frames(320)) * FRAME)]

def test_a_dip_shorter_than_100_ms_does_not_split_speech():
    probs = [0.9] * 10 + [0.1] * 2 + [0.9] * 10 + [0.0] * 10
    assert speech_segments(probs) == [(0, 22 * FRAME)]

def test_a_value_between_the_thresholds_keeps_speech_going():
    probs = [0.9] * 5 + [0.4] * 20 + [0.0] * 10
    assert speech_segments(probs) == [(0, 25 * FRAME)]

def test_speech_running_to_the_end_of_the_window_counts():
    assert speech_segments([0.0] * 3 + [0.8] * 12, 15 * FRAME) == [(3 * FRAME, 15 * FRAME)]

def test_missing_or_altered_model_is_refused(tmp_path):
    with pytest.raises(CueError) as missing:
        SileroVad(tmp_path / "silero_vad.onnx")
    altered = tmp_path / "altered.onnx"
    altered.write_bytes(b"not the pinned model")
    with pytest.raises(CueError) as wrong:
        SileroVad(altered)
    assert missing.value.code == wrong.value.code == "SETUP_REQUIRED"

@needs_model
def test_silence_and_noise_are_not_speech():
    vad = SileroVad(MODEL)
    rng = np.random.default_rng(3)
    assert vad.has_speech(np.zeros(RATE * 3, dtype=np.float32))[0] is False
    noise = rng.normal(0, 0.05, RATE * 5).astype(np.float32)
    speech, detail = vad.has_speech(noise)
    assert speech is False and detail["vad_speech_ms"] == 0

@needs_model
def test_spoken_words_are_speech_even_when_quiet(tmp_path):
    clip = tmp_path / "spoken.wav"
    subprocess.run(["/usr/bin/say", "-o", str(clip), "--file-format=WAVE", "--data-format=LEI16@16000",
                    "Every map is a choice, and every choice tells a story."], check=True)
    audio, rate = sf.read(clip, dtype="float32")
    assert rate == RATE
    vad = SileroVad(MODEL)
    for gain in (1.0, 10 ** (-24 / 20)):
        speech, detail = vad.has_speech(audio * gain)
        assert speech is True and detail["vad_speech_ms"] > 1000

def test_voice_activity_rule_is_part_of_the_cache_key(tmp_path, monkeypatch):
    media = Media("/fixture.mp4", "signature", 1, "stream", 60000, 0, 1, 1)
    monkeypatch.setattr("cue.service.Media.open", lambda path, track: media)
    sup = Supervisor(tmp_path / "runtime", tmp_path / "models", clock=lambda: 100)
    sup.clients["a"] = 100
    first = sup.request("POST", "/v1/sessions", {"request_id": "one", "path": "/fixture.mp4"}, "a")
    monkeypatch.setattr("cue.service.VAD_ID", "a-different-voice-activity-rule")
    second = sup.request("POST", "/v1/sessions", {"request_id": "two", "path": "/fixture.mp4"}, "a")
    profiles = {s.source_profile for s in sup.sessions.values()}
    assert first["session_id"] != second["session_id"]
    assert len(profiles) == 2
