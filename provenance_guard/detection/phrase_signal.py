"""Formulaic phrase-pattern signal.

Scans for lexical and rhetorical templates that appear disproportionately in
generated prose. Deliberately conservative: a single match never yields a high
score. Matches are normalized by length, contributions are capped, and multiple
independent indicators are required for a high score.

Blind spots: academic/corporate writing, human writers who like formal
transitions, and AI text explicitly prompted to avoid these phrases.
"""

from __future__ import annotations

import re

# Documented list of formulaic patterns. Each is matched case-insensitively.
FORMULAIC_PATTERNS: list[str] = [
    r"it is important to note",
    r"it is worth noting",
    r"it's important to remember",
    r"furthermore",
    r"moreover",
    r"in conclusion",
    r"in summary",
    r"to summarize",
    r"plays? a (?:crucial|vital|significant|key|pivotal) role",
    r"multifaceted",
    r"delve into",
    r"navigate the complexities",
    r"in today's (?:fast-paced|digital|modern) world",
    r"a testament to",
    r"it is essential to",
    r"a wide (?:range|array) of",
    r"when it comes to",
    r"on the other hand",
    r"as previously mentioned",
    r"it is crucial to",
    r"the realm of",
    r"foster(?:s|ing)? a",
    r"underscore(?:s|d)? the importance",
    r"paving the way",
    r"in the ever-evolving",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in FORMULAIC_PATTERNS]
_WORD_RE = re.compile(r"[A-Za-z']+")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def analyze(text: str) -> dict:
    """Return ``{score, available, matches}`` for the phrase-pattern signal.

    The score estimates AI likelihood in ``[0, 1]`` based on the density and
    diversity of formulaic phrases, not on any single phrase.
    """
    word_count = len(_WORD_RE.findall(text))
    matches: list[str] = []
    for pattern in _COMPILED:
        found = pattern.findall(text)
        matches.extend(m if isinstance(m, str) else pattern.pattern for m in found)

    distinct_hits = len({m.lower() for m in matches})
    total_hits = len(matches)

    if word_count == 0:
        return {"score": 0.0, "available": True, "matches": []}

    # A single formulaic phrase is not evidence of anything.
    if distinct_hits <= 1:
        base = 0.10 * distinct_hits
        return {
            "score": round(_clamp(base), 4),
            "available": True,
            "matches": matches,
        }

    # Density per 100 words, capped so long formulaic passages don't run away.
    density = total_hits / (word_count / 100.0)
    density_component = _clamp(density / 4.0)  # ~4 hits / 100 words -> saturates

    # Diversity of distinct formulaic constructions.
    diversity_component = _clamp(distinct_hits / 5.0)  # 5 distinct -> saturates

    score = 0.6 * diversity_component + 0.4 * density_component
    # Require genuine corroboration: cap when only two distinct hits.
    if distinct_hits == 2:
        score = min(score, 0.5)

    return {
        "score": round(_clamp(score), 4),
        "available": True,
        "matches": matches,
    }
