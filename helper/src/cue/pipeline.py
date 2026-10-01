from __future__ import annotations
from dataclasses import asdict
import resource
import tempfile
import time
from pathlib import Path
from .backend import Backend
from .core import Cue, CueError, Unit, PREVIOUS_PAIRS, Settings, SOURCE_LANGUAGES, TranslationContext, assemble, drop_seam_phantom, hold_back, pair_previous, sentence_units, validate_units, reconcile_boundary, restore_transcript, transcript_after, join_texts, continues_after
from .glossary import names_hint, proper_nouns, select_entries
from .media import Media, extract
from .vad import SileroVad

# A window whose alignment collapses keeps its aligned part only if that part is
# at least this long; otherwise the window fails as a whole.
MIN_KEPT_MS = 2000

def build_context(units: list[Cue], continues: frozenset[str], job: dict, language: str) -> TranslationContext:
    """Previous lines, glossary entries, misheard spellings and new names for one window."""
    previous_source = [Cue(**c) for c in job.get("previous_source", [])]
    previous_rendered = [Cue(**c) for c in job.get("previous_rendered", [])]
    previous = pair_previous(previous_source, previous_rendered)[-PREVIOUS_PAIRS:]
    glossary = job.get("glossary") or {}
    user, builtin, learned = glossary.get("user", {}), glossary.get("builtin", {}), glossary.get("learned", [])
    known = {source: rendering for source, rendering, *_ in reversed(learned)}
    known.update(user)
    texts = [u.text for u in units]
    previous_texts = [source for source, _ in previous]
    new_names, variants = proper_nouns(texts, previous_texts, known, language, exact=builtin)
    taken = frozenset([*user.values(), *builtin.values(), *(rendering for _, rendering, *_ in learned)])
    if units and previous_source and continues_after(previous_source[-1], units[0]):
        # The previous window ended mid-sentence and this one opens with its continuation.
        continues = continues | {units[0].id}
    return TranslationContext(previous=tuple(previous), glossary=select_entries(user, learned, texts, previous_texts, builtin),
                              variants=variants, new_names=tuple(new_names), continues=continues, taken=taken)

class Pipeline:
    def __init__(self, models: Path, temp: Path, vad_model: Path | None = None, gemma: Path | None = None, asr=None):
        self.backend = Backend(models, gemma, asr=asr)
        # Loaded on first use and kept for the life of the worker.
        self.vad = None
        self.vad_model = vad_model
        self.temp = temp
        self.temp.mkdir(parents=True, exist_ok=True, mode=0o700)

    def has_speech(self, audio) -> tuple[bool, dict]:
        if self.vad is None:
            from .bootstrap import vad_model_path
            self.vad = SileroVad(self.vad_model or vad_model_path())
        return self.vad.has_speech(audio)

    def run(self, job: dict, progress=None) -> dict:
        import numpy as np
        import soundfile as sf
        started = time.monotonic()
        timings = {}
        report = progress or (lambda stage, language=None: None)
        media = Media(**job["media"])
        settings = Settings(**job["settings"])
        start, end = job["range"]
        zero, limit = max(0, start-settings.context_ms), min(media.duration_ms, end+settings.context_ms)
        with tempfile.TemporaryDirectory(dir=self.temp) as tmp:
            wav = Path(tmp)/"span.wav"
            report("extracting")
            t = time.monotonic(); mapping = extract(media, zero, limit, wav); timings["extract_s"] = time.monotonic()-t
            audio, sr = sf.read(wav, dtype="float32")
            if sr != 16000 or len(audio) != mapping["sample_count"]:
                raise CueError("MEDIA_UNSUPPORTED", "PCM sample mapping mismatch")
            # Exact digital silence needs no classifier. Anything else goes to Silero VAD,
            # never to a loudness threshold, so quiet speech and speech under music stay.
            # A window with a cached transcript already had speech.
            silence = bool(np.count_nonzero(audio) == 0)
            no_speech = silence
            language = {"code": "und", "status": "unknown", "method": "digital_silence"}
            if not silence and job.get("cached_source") is None:
                t = time.monotonic(); speech, detail = self.has_speech(audio); timings["vad_s"] = time.monotonic()-t
                timings.update(detail)
                if not speech:
                    no_speech = True
                    language = {"code": "und", "status": "unknown", "method": "voice_activity"}
            source = []
            committed_end = end
            if not no_speech:
                report("loading_model")
                t = time.monotonic(); self.backend.load(); timings["load_s"] = time.monotonic()-t
                cached = job.get("cached_source")
                if cached is not None:
                    source = [Cue(**c) for c in cached["cues"]]; language = cached["language"]
                    report("translating", language)
                    timings["source_cache_hit"] = True
                else:
                    report("transcribing")
                    glossary = job.get("glossary") or {}
                    hint = names_hint(glossary.get("user", {}), glossary.get("learned", []))
                    # What was heard just before this window, written as the language writes it:
                    # a spaced Japanese prompt teaches Whisper to space its own output.
                    earlier = join_texts([c["text"] for c in job.get("previous_source", []) if c.get("text")])
                    t = time.monotonic(); transcript = self.backend.transcribe(wav, settings.source, names=hint, previous=earlier); timings["asr_s"] = time.monotonic()-t
                    report("identifying_language")
                    t = time.monotonic(); language = self.backend.language(transcript, settings.source); timings["lid_s"] = time.monotonic()-t
                    if settings.source == "auto" and language["code"] not in SOURCE_LANGUAGES:
                        # Text LID is tentative because the ASR itself can be
                        # wrong. Let the supervisor retry with more audio and
                        # then leave a coverage hole instead of ending the
                        # session or sending an unsupported code to Qwen.
                        report("identifying_language", language)
                        raise CueError("LANGUAGE_UNCERTAIN", f"unsupported transcript language candidate: {language['code']}")
                    report("aligning", language)
                    t = time.monotonic(); units, cut, skipped = self.backend.align(wav, transcript, language["code"], partial=True, left_ms=start-zero); timings["align_s"] = time.monotonic()-t
                    heard = transcript
                    if skipped:
                        # Words the aligner could not place in the first second belong to the
                        # previous window; the rest of the transcript is this window's.
                        heard = transcript_after(transcript, skipped)
                        if heard is None:
                            raise CueError("ALIGNMENT_FAILED", "incomplete text coverage")
                        timings["left_context_skipped"] = len(skipped)
                    # The aligner works in 80 ms bins, so the last word can end a bin past
                    # the audio, and a transcript can run on past it. Nothing past the audio
                    # is ever committed, so keep the words up to it instead of failing.
                    past = next((i for i, u in enumerate(units) if u.end_ms > limit-zero+50), None)
                    if past is not None:
                        timings["units_past_audio_end"] = len(units)-past
                        units = units[:past]
                    # After a collapse, keep the aligned words before it. The next window
                    # starts at the collapse and transcribes and aligns the rest again.
                    prefix = cut is not None or past is not None
                    validate_units(units, limit-zero, heard, prefix=prefix)
                    timings["quantized_token_groups"] = sum(bool(u.quality_flags) for u in units)
                    punctuated = restore_transcript(units, heard, prefix=prefix)
                    if punctuated is not None:
                        units = punctuated
                    timings["transcript_punctuation_restored"] = punctuated is not None
                    units, dropped = drop_seam_phantom(units, start - zero)
                    if dropped:
                        timings["seam_dropped"] = dropped
                    # Retain the trailing second as a draft until the next window.
                    # If an aligned word straddles that frontier, retain all of it.
                    known_right = job.get("following_source")
                    committed_end = end if end == media.duration_ms or known_right is not None else end-1000
                    if cut is not None:
                        committed_end = min(committed_end, zero+cut)
                        timings["alignment_cut_ms"] = zero+cut
                        if committed_end-start < MIN_KEPT_MS:
                            raise CueError("ALIGNMENT_FAILED", "collapsed alignment left too little to keep")
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
                    previous_cues = job.get("previous_source", [])
                    if previous_cues:
                        # Two windows can measure the word on the seam differently. If the first
                        # owned word crosses the previous cue's end, start it there: that end is
                        # the previous window's measurement of where this word begins. A word
                        # longer than 1.5 s from there was stretched, and still fails below.
                        prior_end = previous_cues[-1]["end_ms"]-zero
                        first = next((i for i, u in enumerate(committed) if (u.start_ms+u.end_ms)/2 >= start-zero), None)
                        if first is not None:
                            u = committed[first]
                            if u.start_ms < prior_end-160 and prior_end < u.end_ms <= prior_end+1500:
                                committed[first] = Unit(prior_end, u.end_ms, u.text, (*u.quality_flags, "start_from_previous_cue"))
                                timings["start_from_previous_cue_ms"] = prior_end-u.start_ms
                    source = assemble(committed, zero, start, committed_end, job["source_profile"], verbatim=punctuated is not None)
                    source, timings["boundary_reused_ms"] = reconcile_boundary(source, [Cue(**c) for c in job.get("previous_source", [])])
                    if source and known_right:
                        next_start = known_right[0]["start_ms"]
                        overlap = source[-1].end_ms-next_start
                        if overlap > 0:
                            if overlap > 160 or next_start <= source[-1].start_ms:
                                raise CueError("ALIGNMENT_FAILED", "cached right boundary time conflict")
                            last=source[-1]; source[-1]=Cue(last.id,last.start_ms,next_start,last.text)
                            timings["boundary_reused_ms"] += overlap
                    if known_right is None and end != media.duration_ms and cut is None:
                        held = hold_back(source, start, committed_end, job.get("min_commit_ms", MIN_KEPT_MS))
                        if held is not None:
                            # The next window re-transcribes the unfinished sentence together
                            # with its continuation. The dropped cues are not cached anywhere.
                            source, hold_start = held
                            timings["held_back_ms"] = committed_end - hold_start
                            committed_end = hold_start
                report("translating", language)
                t = time.monotonic()
                code = language["code"]
                if settings.target not in ("original", code) and source:
                    units, continues = sentence_units(source, settings.target)
                    rendered, names = self.backend.translate(units, settings.target, code, build_context(units, continues, job, code))
                    timings["translation_units"] = len(units)
                else:
                    rendered, names = self.backend.translate(source, settings.target, code)
                timings["translate_s"] = time.monotonic()-t
                timings["names_learned"] = len(names)
                report = getattr(self.backend, "names_report", None) or {}
                if report.get("reported"):
                    timings["names_reported"] = list(report["reported"])
                    timings["names_rejected"] = dict(report.get("rejected", {}))
                if report.get("fallback"):
                    timings["names_fallback"] = True
            else:
                rendered, names = [], {}
            timings["pipeline_s"] = time.monotonic()-started
            timings["rtf"] = timings["pipeline_s"] / ((committed_end-start)/1000)
            timings["process_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            return {"source": [asdict(c) for c in source], "rendered": [asdict(c) for c in rendered], "names": names,
                    "language": language, "timings": timings, "mapping": mapping, "committed_range": [start,committed_end],
                    "coverage_kind": "verified_no_speech" if no_speech else "complete"}

def worker_entry(inbox, outbox, models: str, temp: str, gemma: str | None = None, asr: str | None = None):
    from .asr import MlxAsr
    pipeline = Pipeline(Path(models), Path(temp), gemma=Path(gemma) if gemma else None, asr=MlxAsr(Path(asr)) if asr else None)
    while True:
        job = inbox.get()
        if job is None: break
        try:
            def progress(stage, language=None):
                message = {"job_id": job["job_id"], "stage": stage}
                if language is not None: message["language"] = language
                outbox.put_nowait(message)
            result = pipeline.run(job, progress)
            outbox.put({"job_id": job["job_id"], "result": result})
        except Exception as exc:
            detail = str(exc) if isinstance(exc,CueError) and exc.code in {"ALIGNMENT_FAILED","TRANSLATION_FAILED","LANGUAGE_UNCERTAIN"} else type(exc).__name__
            outbox.put({"job_id": job["job_id"], "error": {"code": exc.code if isinstance(exc, CueError) else "INFERENCE_FAILED", "detail": detail}})
    pipeline.backend.close()
