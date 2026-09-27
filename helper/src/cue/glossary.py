"""Per-film glossary: name heuristics, prompt selection and read-only user files."""
from __future__ import annotations
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re
from .core import _sentence_end, digest

DATA_DIR = Path(__file__).parent / "data"

LATIN_SOURCES = {"en", "de", "es", "fr", "it", "pt"}
MAX_NEW_NAMES = 6
# Whole words in any Latin-script language: letters, with inner apostrophes or hyphens.
WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’\-])*")
# A possessive or a bare trailing apostrophe is not part of the name (Hansen's, Peros').
POSSESSIVE = re.compile(r"['’]s?$")
# Characters that open a quotation or a dialogue line; the word after them starts a sentence.
OPENERS = "\"“‘'([{「『—–-"
STOPWORDS = {"I", "Mr", "Mrs", "Ms", "Dr", "Prof", "Sir", "Madam", "Oh", "Ah", "Well", "Yeah", "Yes", "No", "Okay", "OK",
             "God", "Jesus", "Christ", "Hey", "Hi", "Hello", "Wow", "Please", "Thank", "Thanks", "Sorry",
             "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
             "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
             "The", "A", "An", "And", "But", "So", "Then", "Now", "What", "Why", "How", "Who", "When", "Where", "Which", "If",
             "Because", "You", "We", "They", "He", "She", "It", "This", "That", "There", "Here", "Not", "Just", "Very",
             "Professor", "Doctor", "Mister", "Miss", "Ma'am", "Captain", "Sergeant", "Officer", "Father", "Mother", "Uncle", "Aunt",
             "English", "American", "French", "German", "Spanish", "Italian", "Japanese", "Chinese", "Korean", "Russian", "British", "European",
             "Nobody", "Everybody", "Everyone", "Someone", "Somebody", "Anyone", "Anybody", "Nothing", "Something", "Everything", "Anything", "Alright", "Name"}

def common_words(texts) -> set[str]:
    """Words the source writes in lowercase at least as often as capitalised.

    A capitalised twin of one is not a name; one lowercased mention of a name the
    film otherwise capitalises does not veto it."""
    lower: Counter = Counter()
    upper: Counter = Counter()
    for text in texts:
        for word in WORD.findall(text):
            (lower if word[:1].islower() else upper)[word.lower()] += 1
    return {word for word, count in lower.items() if count >= upper.get(word, 0)}

def is_common_word(name: str, common: set[str]) -> bool:
    return name.split()[0].lower() in common

@lru_cache(maxsize=None)
def builtin_glossary(target: str) -> dict[str, str]:
    """Cue's built-in renderings of common names for a target, or {} when it has none. Read-only."""
    path = DATA_DIR / f"names-{target}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, str)}

def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j-1] + 1, previous[j-1] + (ca != cb)))
        previous = current
    return previous[-1]

def match_name(candidate: str, known) -> str | None:
    """The established spelling a candidate stands for, or None.

    Exact keys win. Otherwise the first letters must agree and the edit distance
    may be 1 when the longer spelling has 4-5 letters, 2 when it has 6 or more.
    Candidates of 3 letters or fewer match exactly only.
    """
    if candidate in known:
        return candidate
    if len(candidate) < 4:
        return None
    folded = candidate.casefold()
    best = None
    for key in known:
        if key[:1].casefold() != folded[:1]:
            continue
        limit = 1 if max(len(candidate), len(key)) <= 5 else 2
        distance = levenshtein(folded, key.casefold())
        if distance <= limit and (best is None or distance < best[0]):
            best = (distance, key)
    return best[1] if best else None

def _shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) > len(letters) / 2

def _candidate(word: str) -> str:
    return POSSESSIVE.sub("", word)

def _is_acronym(token: str) -> bool:
    return 2 <= len(token) <= 5 and token.isalpha() and token.isupper()

def _looks_like_name(token: str) -> bool:
    """Capitalised, at least three characters, letters with inner apostrophes or hyphens (José, Jean-Luc, McCoy)."""
    return (len(token) >= 3 and token[0].isupper() and token[1].islower()
            and all(c.isalpha() or c in "'’-" for c in token[2:]))

def _is_name_token(word: str, shouting: bool) -> bool:
    token = _candidate(word)
    if token in STOPWORDS:
        return False
    if _is_acronym(token):
        return not shouting
    return _looks_like_name(token)

def _runs(text: str) -> list[tuple[list[str], bool]]:
    """Maximal runs of up to three adjacent name tokens as (tokens, first token opens a sentence)."""
    shouting = _shouting(text)
    words = list(WORD.finditer(text))
    runs, i = [], 0
    while i < len(words):
        match = words[i]
        if not _is_name_token(match.group(), shouting):
            i += 1; continue
        raw = text[:match.start()].strip()
        opened = bool(raw) and raw[-1] in OPENERS
        before = raw.rstrip(OPENERS).rstrip()
        initial = not before or opened or _sentence_end(before) or before.endswith("…")
        run, end, j = [_candidate(match.group())], match.end(), i + 1
        while j < len(words) and len(run) < 3 and _is_name_token(words[j].group(), shouting) and text[end:words[j].start()].isspace():
            run.append(_candidate(words[j].group())); end = words[j].end(); j += 1
        runs.append((run, initial))
        i = j
    return runs

def proper_nouns(texts, previous_texts, known, language: str, limit: int | None = MAX_NEW_NAMES,
                 exact: dict[str, str] | None = None) -> tuple[list[str], dict[str, str]]:
    """New proper-noun candidates in texts, and misheard spellings of known names.

    Latin-script sources only. A capitalised word that opens a sentence ("Meet",
    "Ask", or a name) counts only when the same word also appears mid-sentence in
    texts or previous_texts; otherwise the run starts at the next token, so
    "Meet John Nash." yields "John Nash". `known` names (user and learned) also
    match misheard spellings; `exact` names (the built-in table) match exactly
    only, because near misses among hundreds of common names are mostly wrong.
    Returns (new_names, {misheard: established}).
    """
    if language not in LATIN_SOURCES:
        return [], {}
    exact = exact or {}
    def establish(token: str) -> str | None:
        return token if token in exact else match_name(token, known)
    common = common_words([*texts, *previous_texts])
    non_initial: set[str] = set()
    for text in [*texts, *previous_texts]:
        for tokens, initial in _runs(text):
            non_initial.update(tokens[1:] if initial else tokens)
    new: list[str] = []
    variants: dict[str, str] = {}
    seen: set[str] = set()
    for text in texts:
        for tokens, initial in _runs(text):
            if initial and tokens[0] not in non_initial:
                tokens = tokens[1:]
            if not tokens:
                continue
            if len(tokens) > 1 and any(establish(token) is not None for token in tokens):
                # A phrase with established parts is not learned whole: misheard parts
                # become variant notes and only the unknown parts are asked for alone.
                pieces = []
                for token in tokens:
                    match = establish(token)
                    if match is None:
                        pieces.append(token)
                    elif match != token:
                        variants[token] = match
            else:
                pieces = [" ".join(tokens)]
            for candidate in pieces:
                if candidate in seen or is_common_word(candidate, common):
                    continue
                seen.add(candidate)
                match = establish(candidate)
                if match == candidate:
                    continue
                if match is not None:
                    variants[candidate] = match
                elif limit is None or len(new) < limit:
                    new.append(candidate)
    return new, variants

MAX_PROMPT_ENTRIES = 40
RECENT_ENTRIES = 10
MAX_HINT_NAMES = 20
MAX_FILE_BYTES = 256 * 1024
MAX_ENTRIES = 1000
MAX_TEXT = 64
KANA = re.compile("[぀-ヿ]")
NO_KANA_TARGETS = {"zh-TW", "zh-CN", "ko"}

def select_entries(user: dict[str, str], learned: list, texts, previous_texts, builtin: dict[str, str] | None = None) -> dict[str, str]:
    """Entries worth showing for one batch: the relevant ones (user, then built-in, then learned),
    then the most recent learned ones, at most 40."""
    corpus = " ".join([*texts, *previous_texts])
    ordered = [*user.items(), *(builtin or {}).items(), *((source, rendering) for source, rendering, *_ in learned)]
    # Misheard spellings only ever map to user and learned names; built-in names must appear as written.
    fuzzy_keys = [*user, *(source for source, *_ in learned)]
    tokens = {_candidate(match.group()) for match in WORD.finditer(corpus)}
    matched = {match_name(token, fuzzy_keys) for token in tokens} - {None}
    def present(key: str) -> bool:
        return re.search(rf"(?<![^\W\d_]){re.escape(key)}(?![^\W\d_])", corpus, re.IGNORECASE) is not None
    chosen: dict[str, str] = {}
    for source, rendering in ordered:
        if source in matched or present(source):
            chosen.setdefault(source, rendering)
    for source, rendering, *_ in learned[:RECENT_ENTRIES]:
        chosen.setdefault(source, rendering)
    return dict(list(chosen.items())[:MAX_PROMPT_ENTRIES])

def names_hint(user: dict[str, str], learned: list) -> list[str]:
    """Source spellings for the ASR prompt: user entries first, then the most recent learned ones."""
    names = list(user)
    names.extend(source for source, *_ in learned if source not in user)
    return names[:MAX_HINT_NAMES]

def glossary_hash(mapping: dict[str, str]) -> str:
    return digest(mapping) if mapping else "none"

def sidecar_path(media_path: str) -> Path:
    video = Path(media_path)
    return video.with_name(video.stem + ".cue-glossary.json")

def _log_invalid(scope: str) -> None:
    print(json.dumps({"event": "glossary_invalid", "scope": scope}), flush=True)

def _read_section(path: Path, target: str, scope: str, log) -> dict[str, str]:
    """One target's entries from a user file, or {} when the file is absent or invalid."""
    if path.is_symlink():
        log(scope); return {}
    if not path.exists():
        return {}
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("not a regular file within the size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or sum(len(v) for v in data.values() if isinstance(v, dict)) > MAX_ENTRIES:
            raise ValueError("shape")
        section = data.get(target, {})
        if not isinstance(section, dict):
            raise ValueError("section")
        clean: dict[str, str] = {}
        for key, value in section.items():
            if not (isinstance(key, str) and isinstance(value, str) and 1 <= len(key) <= MAX_TEXT and 1 <= len(value) <= MAX_TEXT):
                raise ValueError("entry")
            if target in NO_KANA_TARGETS and KANA.search(value):
                raise ValueError("kana in a target that forbids it")
            clean[key] = value
        return clean
    except (OSError, ValueError):
        log(scope)
        return {}

def load_user_glossary(media_path: str, root: Path, target: str, log=None) -> dict[str, str]:
    """Merged user entries for one target. The sidecar next to the video overrides the global file.
    Both files are only ever read."""
    log = log or _log_invalid
    merged: dict[str, str] = {}
    merged.update(_read_section(root / "glossary.json", target, "global", log))
    merged.update(_read_section(sidecar_path(media_path), target, "sidecar", log))
    return merged
