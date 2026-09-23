from __future__ import annotations
from dataclasses import asdict
import resource
import tempfile
import time
from pathlib import Path
from .backend import Backend
from .core import Cue, CueError, Settings, assemble, validate_units, reconcile_boundary
from .media import Media, extract

class Pipeline:
    def __init__(self, models: Path, temp: Path):
        self.backend = Backend(models)
        self.temp = temp
        self.temp.mkdir(parents=True, exist_ok=True, mode=0o700)

    def run(self, job: dict) -> dict:
        import numpy as np
        import soundfile as sf
        started = time.monotonic()
        timings = {}
        media = Media(**job["media"])
        settings = Settings(**job["settings"])
        start, end = job["range"]
        zero, limit = max(0, start-settings.context_ms), min(media.duration_ms, end+settings.context_ms)
        with tempfile.TemporaryDirectory(dir=self.temp) as tmp:
            wav = Path(tmp)/"span.wav"
            t = time.monotonic(); mapping = extract(media, zero, limit, wav); timings["extract_s"] = time.monotonic()-t
            audio, sr = sf.read(wav, dtype="float32")
            if sr != 16000 or len(audio) != mapping["sample_count"]:
                raise CueError("MEDIA_UNSUPPORTED", "PCM sample mapping mismatch")
            # Only exact digital silence may bypass inference without a speech classifier.
            # Music/quiet speech never gets declared silent based on a loudness threshold.
            silence = bool(np.count_nonzero(audio) == 0)
            language = {"code": "und", "status": "unknown", "method": "digital_silence"}
            source = []
            committed_end = end
            if not silence:
                t = time.monotonic(); self.backend.load(); timings["load_s"] = time.monotonic()-t
                cached = job.get("cached_source")
                if cached is not None:
                    source = [Cue(**c) for c in cached["cues"]]; language = cached["language"]
                    timings["source_cache_hit"] = True
                else:
                    t = time.monotonic(); transcript = self.backend.transcribe(wav); timings["asr_s"] = time.monotonic()-t
                    t = time.monotonic(); language = self.backend.language(transcript, settings.source); timings["lid_s"] = time.monotonic()-t
                    t = time.monotonic(); units = self.backend.align(wav, transcript, language["code"]); timings["align_s"] = time.monotonic()-t
                    validate_units(units, limit-zero, transcript)
                    timings["quantized_token_groups"] = sum(bool(u.quality_flags) for u in units)
                    # Retain the trailing second as a draft until the next window.
                    # If an aligned word straddles that frontier, retain all of it.
                    known_right = job.get("following_source")
                    committed_end = end if end == media.duration_ms or known_right is not None else end-1000
                    crossing = [u.start_ms+zero for u in units if u.start_ms+zero < committed_end < u.end_ms+zero]
                    if crossing and known_right is None: committed_end = min(crossing)
                    elif crossing:
                        # The right-hand chunk is already committed. Fresh ASR
                        # over overlapping context may phrase its first word
                        # differently. Never invent an end time or overwrite
                        # the cached cue: discard only units crossing this
                        # seam, record their count, then keep processing.
                        timings["boundary_discarded_units"] = len(crossing)
                    if committed_end <= start: raise CueError("ALIGNMENT_FAILED", "unresolved boundary made no progress")
                    committed = [u for u in units if u.end_ms+zero <= committed_end]
                    source = assemble(committed, zero, start, committed_end, job["source_profile"])
                    source, timings["boundary_reused_ms"] = reconcile_boundary(source, [Cue(**c) for c in job.get("previous_source", [])])
                    if source and known_right:
                        next_start = known_right[0]["start_ms"]
                        overlap = source[-1].end_ms-next_start
                        if overlap > 0:
                            if overlap > 160 or next_start <= source[-1].start_ms:
                                raise CueError("ALIGNMENT_FAILED", "cached right boundary time conflict")
                            last=source[-1]; source[-1]=Cue(last.id,last.start_ms,next_start,last.text)
                            timings["boundary_reused_ms"] += overlap
                t = time.monotonic(); rendered = self.backend.translate(source, settings.target, language["code"]); timings["translate_s"] = time.monotonic()-t
            else:
                rendered = []
            timings["pipeline_s"] = time.monotonic()-started
            timings["rtf"] = timings["pipeline_s"] / ((committed_end-start)/1000)
            timings["process_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return {"source": [asdict(c) for c in source], "rendered": [asdict(c) for c in rendered],
                    "language": language, "timings": timings, "mapping": mapping, "committed_range": [start,committed_end],
                    "coverage_kind": "verified_no_speech" if silence else "complete"}

def worker_entry(inbox, outbox, models: str, temp: str):
    pipeline = Pipeline(Path(models), Path(temp))
    while True:
        job = inbox.get()
        if job is None: break
        try:
            result = pipeline.run(job)
            outbox.put({"job_id": job["job_id"], "result": result})
        except Exception as exc:
            detail = str(exc) if isinstance(exc,CueError) and exc.code in {"ALIGNMENT_FAILED","TRANSLATION_FAILED","LANGUAGE_UNCERTAIN"} else type(exc).__name__
            outbox.put({"job_id": job["job_id"], "error": {"code": exc.code if isinstance(exc, CueError) else "INFERENCE_FAILED", "detail": detail}})
    pipeline.backend.close()
