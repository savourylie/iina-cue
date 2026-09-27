"""Human-readable evaluation of cached captions: source beside translation, names, fragments."""
from __future__ import annotations
import json
import re
from .core import Cue, join_texts, stamp
from .glossary import proper_nouns
from .storage import Cache

def latest_profile(cache: Cache, media: str, target: str) -> str | None:
    """The profile for this media and target whose chunks were written most recently."""
    row = cache.db.execute(
        "SELECT p.profile FROM profiles p JOIN chunks c ON c.profile=p.profile WHERE p.media=? AND p.target=? "
        "GROUP BY p.profile ORDER BY MAX(c.updated) DESC, MAX(c.rowid) DESC LIMIT 1", (media, target)).fetchone()
    return row[0] if row else None

def chunks(cache: Cache, profile: str) -> list[tuple[int, int, list[Cue]]]:
    return [(start, end, [Cue(**c) for c in json.loads(payload)["cues"]])
            for start, end, payload in cache.db.execute("SELECT start,end,payload FROM chunks WHERE profile=? ORDER BY start", (profile,))]

def source_language(cache: Cache, profile: str) -> str:
    for (payload,) in cache.db.execute("SELECT payload FROM chunks WHERE profile=? ORDER BY start", (profile,)):
        code = json.loads(payload)["language"].get("code")
        if code and code != "und":
            return code
    return "en"

def inside(source: list[Cue], start: int, end: int) -> list[Cue]:
    """Source cues whose midpoint lies in [start, end)."""
    return [c for c in source if start <= (c.start_ms + c.end_ms) / 2 < end]

def side_by_side(source: list[Cue], rendered_chunks, from_ms: int = 0, to_ms: int | None = None) -> list[str]:
    lines = []
    for start, end, rendered in rendered_chunks:
        if end <= from_ms or (to_ms is not None and start >= to_ms):
            continue
        lines.append(f"--- window {stamp(start)}-{stamp(end)} ---")
        covered: set[str] = set()
        for cue in rendered:
            sources = inside(source, cue.start_ms, cue.end_ms + 1)
            covered.update(c.id for c in sources)
            lines.append(f"[{stamp(cue.start_ms)}-{stamp(cue.end_ms)}] {join_texts([c.text for c in sources]) or '(no source cue)'}")
            lines.append(f"    => {cue.text}")
        for cue in inside(source, start, end):
            if cue.id not in covered:
                lines.append(f"[{stamp(cue.start_ms)}-{stamp(cue.end_ms)}] {cue.text}")
                lines.append("    => (no caption)")
    return lines

def name_table(source: list[Cue], rendered: list[Cue], glossary: dict[str, str], language: str = "en") -> list[dict]:
    """For each glossary key and detected proper noun: mentions, captions covering them, and how many
    captions contain the established rendering (None when there is no established rendering)."""
    candidates, _ = proper_nouns([c.text for c in source], [], {}, language, limit=None)
    rows = []
    for name in [*glossary, *[c for c in candidates if c not in glossary]]:
        pattern = re.compile(rf"(?<![^\W\d_]){re.escape(name)}(?![^\W\d_])")
        mentions = [c for c in source if pattern.search(c.text)]
        if not mentions:
            continue
        captions = []
        for cue in mentions:
            mid = (cue.start_ms + cue.end_ms) / 2
            captions.extend(r.text for r in rendered if r.start_ms <= mid < r.end_ms + 1)
        rendering = glossary.get(name)
        rows.append({"name": name, "rendering": rendering, "mentions": len(mentions), "captions": len(captions),
                     "consistent": sum(rendering in text for text in captions) if rendering else None, "samples": captions[:3]})
    return rows

def fragment_count(source: list[Cue], rendered: list[Cue]) -> int:
    """Captions whose source has fewer than three words."""
    return sum(len(join_texts([c.text for c in inside(source, r.start_ms, r.end_ms + 1)]).split()) < 3 for r in rendered)

def dump_report(cache: Cache, media_signature: str, target: str, user_glossary: dict[str, str], from_ms: int = 0, to_ms: int | None = None) -> str:
    source_profile = latest_profile(cache, media_signature, "original")
    profile = latest_profile(cache, media_signature, target)
    if not source_profile or not profile:
        return f"no cached captions for this media and target {target}"
    source = sorted({c.id: c for _, _, cues in chunks(cache, source_profile) for c in cues}.values(), key=lambda c: (c.start_ms, c.end_ms))
    rendered_chunks = chunks(cache, profile)
    rendered = [c for _, _, cues in rendered_chunks for c in cues]
    learned = {s: r for s, r, *_ in reversed(cache.names(media_signature, target))}
    glossary = {**learned, **user_glossary}
    lines = [f"source profile {source_profile[:12]}  target profile {profile[:12]} ({target})",
             *side_by_side(source, rendered_chunks, from_ms, to_ms), "", "--- names ---"]
    for row in name_table(source, rendered, glossary, source_language(cache, source_profile)):
        status = "" if row["consistent"] is None else f" consistent {row['consistent']}/{row['captions']}"
        lines.append(f"{row['name']} => {row['rendering'] or '?'}  mentions {row['mentions']}{status}")
        lines.extend(f"    {sample}" for sample in row["samples"])
    lines.append(f"--- captions with fewer than 3 source words: {fragment_count(source, rendered)} of {len(rendered)} ---")
    return "\n".join(lines)
