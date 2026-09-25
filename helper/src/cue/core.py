"""Pure timeline, alignment, coverage and subtitle contracts."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import unicodedata

class CueError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code

# Exact source languages declared by the pinned Qwen3 ForcedAligner model.
# Languages beyond the original four-language acceptance set are experimental.
SOURCE_LANGUAGES = {"zh": "Chinese", "yue": "Cantonese", "en": "English",
                    "de": "German", "es": "Spanish", "fr": "French", "it": "Italian",
                    "pt": "Portuguese", "ru": "Russian", "ko": "Korean", "ja": "Japanese"}

def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def ranges_merge(ranges: list[list[int]]) -> list[list[int]]:
    out: list[list[int]] = []
    for a, b in sorted(ranges):
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b):
            raise ValueError("invalid half-open interval")
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out

def continuous_end(ranges: list[list[int]], position: int) -> int:
    for a, b in ranges_merge(ranges):
        if a <= position < b:
            return b
    return position

@dataclass(frozen=True)
class Settings:
    target: str = "zh-TW"
    source: str = "auto"
    startup_ms: int = 8000
    high_ms: int = 60000
    first_ms: int = 10000
    window_ms: int = 16000
    context_ms: int = 1000

    def __post_init__(self):
        if self.target not in {"original", "zh-TW", "zh-CN", "en", "ja", "ko"} or (self.source != "auto" and self.source not in SOURCE_LANGUAGES):
            raise CueError("INVALID_SETTINGS")
        if not 0 < self.startup_ms <= self.high_ms or not 0 < self.first_ms <= 24000 or not 0 < self.window_ms <= 24000:
            raise CueError("INVALID_SETTINGS")

@dataclass(frozen=True)
class Unit:
    start_ms: int
    end_ms: int
    text: str
    quality_flags: tuple[str, ...] = ()

def coalesce_until_collapse(units: list[Unit]) -> tuple[list[Unit], int | None, str | None]:
    """Keep Qwen's measured outer boundaries when sub-word bins collapse.

    No duration is guessed or distributed. A zero-length token is included in
    an adjacent multi-token span; raw standalone zero intervals stay invalid.
    Stops at the first run that cannot be placed and returns the units before
    it, the time where that run begins, and why. A trailing run also drops the
    word before it, because that word's end was stretched over the run.
    """
    out: list[Unit] = []
    pending: list[Unit] = []
    for u in units:
        if u.start_ms == u.end_ms:
            pending.append(u)
            continue
        if pending:
            if len(pending) > 3 or u.end_ms-pending[0].start_ms > 1500:
                return out, pending[0].start_ms, "collapsed alignment span"
            u = Unit(pending[0].start_ms, u.end_ms, " ".join(x.text for x in pending)+" "+u.text, ("quantized_tokens_coalesced",))
            pending = []
        out.append(u)
    if pending:
        if not out or len(pending) > 3 or pending[-1].end_ms-out[-1].start_ms > 1500:
            if not out:
                return [], pending[0].start_ms, "collapsed trailing alignment"
            stretched = out.pop()
            return out, stretched.start_ms, "collapsed trailing alignment"
        last=out.pop()
        out.append(Unit(last.start_ms, max(last.end_ms,pending[-1].end_ms), last.text+" "+" ".join(u.text for u in pending), ("quantized_tokens_coalesced",)))
    return out, None, None

def coalesce_quantized_units(units: list[Unit]) -> list[Unit]:
    """All-or-nothing form of coalesce_until_collapse: any collapse fails the window."""
    kept, cut, reason = coalesce_until_collapse(units)
    if cut is not None:
        raise CueError("ALIGNMENT_FAILED", reason)
    return kept

@dataclass(frozen=True)
class Cue:
    id: str
    start_ms: int
    end_ms: int
    text: str

def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]*>|\{[^}]*\}", "", text)
    return re.sub(r"[\x00-\x1f\x7f]", " ", text).strip()

def validate_units(units: list[Unit], duration_ms: int, source: str, prefix: bool = False) -> None:
    if not units or not source.strip():
        raise CueError("ALIGNMENT_FAILED", "empty alignment")
    previous = -1
    for unit in units:
        if not all(math.isfinite(t) for t in (unit.start_ms, unit.end_ms)) or not 0 <= unit.start_ms < unit.end_ms <= duration_ms + 50:
            raise CueError("ALIGNMENT_FAILED", "invalid alignment time")
        if unit.start_ms < previous or not unit.text.strip():
            raise CueError("ALIGNMENT_FAILED", "non-monotonic or empty alignment")
        previous = unit.end_ms
    normalize = lambda s: "".join(c for c in s.casefold() if c.isalnum())
    aligned = normalize("".join(u.text for u in units))
    # The aligner must account for the actual transcript. A kept prefix (after a
    # collapse) must spell out its beginning; the next window prepares the rest.
    expected = normalize(source)
    if not (aligned == expected or (prefix and aligned and expected.startswith(aligned))):
        raise CueError("ALIGNMENT_FAILED", "incomplete text coverage")

def restore_transcript(units: list[Unit], transcript: str, prefix: bool = False) -> list[Unit] | None:
    """Put ASR punctuation back on aligned words without changing their times.

    Qwen commonly returns the spoken words without punctuation. The validated
    alphanumeric sequence lets us assign each original transcript span to an
    aligned unit. If a boundary cannot be mapped exactly, use the aligner's
    text rather than guessing a word time or dropping speech.
    """
    positions = [i for i, char in enumerate(transcript)
                 for folded in char.casefold() if folded.isalnum()]
    lengths = [sum(char.isalnum() for char in unit.text.casefold()) for unit in units]
    if prefix:
        # Only the start of the transcript was aligned; map the units onto that part.
        positions = positions[:sum(lengths)]
    if not units or any(length == 0 for length in lengths) or sum(lengths) != len(positions):
        return None
    spans = []
    offset = 0
    for length in lengths:
        spans.append((positions[offset], positions[offset + length - 1] + 1))
        offset += length
    if any(right > next_left for (_, right), (next_left, _) in zip(spans, spans[1:])):
        return None
    boundaries = []
    for (_, right), (next_left, _) in zip(spans, spans[1:]):
        gap = transcript[right:next_left]
        split = len(gap.rstrip())
        # A quote/bracket after whitespace opens the next phrase; a quote
        # immediately after a word or punctuation closes the current one.
        opener = re.search(r'\s+(?=["“‘(\[{]+$)', gap[:split])
        if opener:
            split = opener.start()
        boundaries.append(right + split)
    if prefix:
        # The last kept word takes its closing punctuation, never the next phrase's opener.
        end = spans[-1][1]
        while end < len(transcript) and not transcript[end].isalnum() and not transcript[end].isspace() and transcript[end] not in "\"“‘([{「『":
            end += 1
        boundaries.append(end)
    else:
        boundaries.append(len(transcript))
    cursor = 0
    restored = []
    for unit, boundary in zip(units, boundaries):
        restored.append(Unit(unit.start_ms, unit.end_ms, transcript[cursor:boundary], unit.quality_flags))
        cursor = boundary
    return restored

def _subtitle_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)

def _sentence_end(text: str) -> bool:
    tail = text.rstrip().rstrip('\'"”’)]}】」』')
    if not tail.endswith((".", "!", "?", "。", "！", "？")):
        return False
    if tail.endswith(".") and re.search(r"(?i)(?:\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs)|\b[A-Z])\.$", tail):
        return False
    return True

def _clause_end(text: str) -> bool:
    return text.rstrip().rstrip('\'"”’)]}】」』').endswith((",", ";", ":", "，", "、", "；", "："))

def _weak_ending(text: str) -> bool:
    if text.rstrip().endswith(("'", "’", "-", "‐")):
        return True
    words = re.findall(r"[A-Za-z]+", text)
    return bool(words and words[-1].casefold() in {
        "a", "an", "the", "and", "or", "but", "to", "of", "for", "with", "from",
        "in", "on", "at", "by", "as", "is", "are", "was", "were", "have", "has",
        "had", "will", "would", "can", "could", "should", "not", "i"})

def assemble(units: list[Unit], zero_ms: int, core_start: int, core_end: int, source_key: str, *, verbatim: bool = False) -> list[Cue]:
    owned = [u for u in units if core_start <= zero_ms + (u.start_ms + u.end_ms) / 2 < core_end]
    groups: list[list[Unit]] = []
    current: list[Unit] = []
    def rendered(group: list[Unit]) -> str:
        if verbatim:
            return "".join(unit.text for unit in group).strip()
        text = " ".join(unit.text for unit in group)
        return re.sub(r"(?<=[\u3000-\u9fff]) (?=[\u3000-\u9fff])", "", text).strip()
    for u in owned:
        if current and u.start_ms - current[-1].end_ms > 600:
            groups.append(current); current = []
        while current and (u.end_ms - current[0].start_ms > 4500
                           or _subtitle_width(rendered([*current, u])) > 64):
            cut = len(current)
            while cut > 1 and _weak_ending(rendered(current[:cut])):
                earlier = current[:cut-1]
                if _subtitle_width(rendered(earlier)) < 20 or earlier[-1].end_ms-earlier[0].start_ms < 800:
                    break
                cut -= 1
            groups.append(current[:cut]); current = current[cut:]
        current.append(u)
        text = rendered(current)
        if _sentence_end(text) or (_clause_end(text) and
                                   (_subtitle_width(text) >= 28 or current[-1].end_ms - current[0].start_ms >= 1800)):
            groups.append(current); current = []
    if current:
        groups.append(current)
    # A very short measured phrase would flash on screen. Borrow reading time
    # by joining an adjacent cue only when its already-measured outer word
    # boundaries still fit the layout limits. No timestamp is extended.
    i = 0
    while i < len(groups):
        group = groups[i]
        if group[-1].end_ms - group[0].start_ms >= 700:
            i += 1; continue
        choices = []
        for neighbor in (i-1, i+1):
            if not 0 <= neighbor < len(groups):
                continue
            left, right = (groups[neighbor], group) if neighbor < i else (group, groups[neighbor])
            gap = right[0].start_ms - left[-1].end_ms
            combined = [*left, *right]
            if gap > 600 or combined[-1].end_ms-combined[0].start_ms > 4500 or _subtitle_width(rendered(combined)) > 64:
                continue
            # Prefer a join within a sentence, then the smallest pause.
            choices.append((_sentence_end(rendered(left)), gap, _subtitle_width(rendered(combined)), neighbor, combined))
        if not choices:
            i += 1; continue
        _, _, _, neighbor, combined = min(choices, key=lambda choice: choice[:3])
        low = min(i, neighbor)
        groups[low:low+2] = [combined]
        i = max(0, low-1)
    out = []
    for group in groups:
        text = rendered(group)
        start, end = zero_ms + group[0].start_ms, zero_ms + group[-1].end_ms
        # Ownership determines inclusion. Actual aligned times remain intact.
        out.append(Cue(digest([source_key, start, end, text])[:24], start, end, clean_text(text)))
    return out

def reconcile_boundary(cues: list[Cue], previous: list[Cue]) -> tuple[list[Cue], int]:
    """Resolve at most two 80 ms aligner bins against a committed boundary.

    The reused timestamp is an already measured source end, not an estimated
    word duration. Larger conflicts remain errors; committed cues never move.
    """
    if not cues or not previous: return cues, 0
    prior = previous[-1]
    first = cues[0]
    overlap = prior.end_ms-first.start_ms
    if overlap <= 0: return cues, 0
    if overlap > 160 or prior.end_ms >= first.end_ms:
        raise CueError("ALIGNMENT_FAILED", "unresolved chunk boundary")
    return [Cue(first.id, prior.end_ms, first.end_ms, first.text), *cues[1:]], overlap

def translation_parse(raw: str, cues: list[Cue]) -> dict[str, str]:
    raw = raw.strip()
    if raw.startswith("```json") and raw.endswith("```"):
        raw = raw[7:-3].strip()
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) != len(cues):
            raise ValueError()
        result = {}
        for row in data:
            if set(row) != {"id", "text"} or not isinstance(row["text"], str) or row["id"] in result:
                raise ValueError()
            text = clean_text(row["text"])
            if not text or len(text) > 1000 or any(x in text for x in ("<think", "[THOUGHT]")):
                raise ValueError()
            result[row["id"]] = text
        if set(result) != {c.id for c in cues}:
            raise ValueError()
        return result
    except (TypeError, ValueError, KeyError) as exc:
        raise CueError("TRANSLATION_FAILED", "invalid cue IDs or JSON") from exc

def stamp(ms: int) -> str:
    if ms < 0:
        raise ValueError("negative timestamp")
    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

def srt(cues: list[Cue]) -> str:
    out = []
    previous = -1
    for cue in sorted(cues, key=lambda c: (c.start_ms, c.end_ms, c.id)):
        if cue.start_ms < previous or cue.start_ms >= cue.end_ms:
            raise CueError("ALIGNMENT_FAILED", "overlapping or invalid cues")
        previous = cue.end_ms
        out.append(f"{len(out)+1}\n{stamp(cue.start_ms)} --> {stamp(cue.end_ms)}\n{clean_text(cue.text)}\n")
    return "\n".join(out)

def next_window(ranges: list[list[int]], position: int, duration: int, settings: Settings, rate: float = 1) -> tuple[int, int] | None:
    end = continuous_end(ranges, position)
    horizon = min(duration, position + min(120000, int(settings.high_ms * rate)))
    if end >= horizon:
        return None
    length = settings.first_ms if end == position else settings.window_ms
    following = [a for a, _ in ranges if a > end]
    # High water decides whether to start another bounded job. Do not shorten
    # that job into a tiny tail: the alignment draft needs right-side context.
    return end, min(end + length, duration, min(following, default=duration))
