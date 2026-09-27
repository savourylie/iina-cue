"""Per-film glossary: name heuristics, prompt selection and read-only user files."""
from __future__ import annotations
import json
from pathlib import Path
import re
from .core import _sentence_end, digest

LATIN_SOURCES = {"en", "de", "es", "fr", "it", "pt"}
MAX_NEW_NAMES = 6
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
NAME_TOKEN = re.compile(r"[A-Z][a-z][A-Za-z'’\-]+|[A-Z]{2,5}")
ACRONYM = re.compile(r"[A-Z]{2,5}")
POSSESSIVE = re.compile(r"['’]s$")
STOPWORDS = {"I", "Mr", "Mrs", "Ms", "Dr", "Prof", "Sir", "Madam", "Oh", "Ah", "Well", "Yeah", "Yes", "No", "Okay", "OK",
             "God", "Jesus", "Christ", "Hey", "Hi", "Hello", "Wow", "Please", "Thank", "Thanks", "Sorry",
             "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
             "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
             "The", "A", "An", "And", "But", "So", "Then", "Now", "What", "Why", "How", "Who", "When", "Where", "Which", "If",
             "Because", "You", "We", "They", "He", "She", "It", "This", "That", "There", "Here", "Not", "Just", "Very"}

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

def _is_name_token(word: str, shouting: bool) -> bool:
    token = _candidate(word)
    if token in STOPWORDS or not NAME_TOKEN.fullmatch(token):
        return False
    return not (shouting and ACRONYM.fullmatch(token))

def _runs(text: str) -> list[tuple[list[str], bool]]:
    """Maximal runs of up to three adjacent name tokens as (tokens, first token opens a sentence)."""
    shouting = _shouting(text)
    words = list(WORD.finditer(text))
    runs, i = [], 0
    while i < len(words):
        match = words[i]
        if not _is_name_token(match.group(), shouting):
            i += 1; continue
        before = text[:match.start()].strip()
        initial = not before or _sentence_end(before)
        run, end, j = [_candidate(match.group())], match.end(), i + 1
        while j < len(words) and len(run) < 3 and _is_name_token(words[j].group(), shouting) and text[end:words[j].start()].isspace():
            run.append(_candidate(words[j].group())); end = words[j].end(); j += 1
        runs.append((run, initial))
        i = j
    return runs

def proper_nouns(texts, previous_texts, known, language: str, limit: int | None = MAX_NEW_NAMES) -> tuple[list[str], dict[str, str]]:
    """New proper-noun candidates in texts, and misheard spellings of known names.

    Latin-script sources only. A capitalised word that opens a sentence ("Meet",
    "Ask", or a name) counts only when the same word also appears mid-sentence in
    texts or previous_texts; otherwise the run starts at the next token, so
    "Meet John Nash." yields "John Nash". Returns (new_names, {misheard: established}).
    """
    if language not in LATIN_SOURCES:
        return [], {}
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
            candidate = " ".join(tokens)
            if candidate in seen:
                continue
            seen.add(candidate)
            match = match_name(candidate, known)
            if match == candidate:
                continue
            if match is not None:
                variants[candidate] = match
            elif limit is None or len(new) < limit:
                new.append(candidate)
    return new, variants
