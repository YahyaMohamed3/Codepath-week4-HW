"""Stylometric uniformity signal (pure Python, no ML downloads).

Measures structural properties of prose. Unusually uniform writing (low variance
in sentence length, low vocabulary diversity, repeated openings) is treated as
more AI-like; irregular, varied writing is treated as more human-like.

Blind spots: academic writing, edited professional copy, poetry, deliberately
repetitive writing, and very short text.
"""

from __future__ import annotations

import math
import re
import statistics

_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"[A-Za-z']+")
_PUNCT_RE = re.compile(r"[,;:\-—()\"']")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text)]
    return [p for p in parts if p]


def compute_metrics(text: str) -> dict:
    """Compute raw stylometric metrics for a passage."""
    words = _WORD_RE.findall(text.lower())
    word_count = len(words)
    sentences = _split_sentences(text)
    sentence_count = len(sentences)

    sentence_lengths = [len(_WORD_RE.findall(s)) for s in sentences]
    sentence_lengths = [n for n in sentence_lengths if n > 0]

    avg_sentence_length = (
        statistics.fmean(sentence_lengths) if sentence_lengths else 0.0
    )
    sentence_length_stdev = (
        statistics.pstdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
    )
    coeff_variation = (
        sentence_length_stdev / avg_sentence_length
        if avg_sentence_length > 0
        else 0.0
    )

    unique_words = len(set(words))
    type_token_ratio = unique_words / word_count if word_count else 0.0

    punctuation_count = len(_PUNCT_RE.findall(text))
    punctuation_density = punctuation_count / word_count if word_count else 0.0

    # Repeated sentence openings: fraction of sentences whose first word repeats.
    openings = [
        _WORD_RE.findall(s.lower())[0]
        for s in sentences
        if _WORD_RE.findall(s.lower())
    ]
    repeated_opening_ratio = 0.0
    if openings:
        distinct = len(set(openings))
        repeated_opening_ratio = 1.0 - (distinct / len(openings))

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_sentence_length": round(avg_sentence_length, 3),
        "sentence_length_stdev": round(sentence_length_stdev, 3),
        "sentence_length_cv": round(coeff_variation, 3),
        "type_token_ratio": round(type_token_ratio, 3),
        "punctuation_density": round(punctuation_density, 3),
        "repeated_opening_ratio": round(repeated_opening_ratio, 3),
    }


def analyze(text: str) -> dict:
    """Return ``{score, available, metrics}`` for the stylometric signal.

    The score is an estimated AI likelihood in ``[0, 1]``: higher means more
    uniform / more AI-like.
    """
    metrics = compute_metrics(text)

    # Too little structure to judge -> low-confidence, near-neutral score.
    if metrics["word_count"] < 20 or metrics["sentence_count"] < 2:
        return {"score": 0.5, "available": True, "metrics": metrics}

    # Component 1: sentence-length coefficient of variation.
    # Human prose typically has CV ~0.5-0.9; very low CV is uniform/AI-like.
    cv = metrics["sentence_length_cv"]
    uniformity = _clamp(1.0 - (cv / 0.75))  # cv>=0.75 -> 0, cv=0 -> 1

    # Component 2: type-token ratio. Low diversity (relative to length) is more
    # AI-like, but long texts naturally have lower TTR, so scale expectation.
    ttr = metrics["type_token_ratio"]
    wc = metrics["word_count"]
    expected_ttr = _clamp(0.7 - 0.12 * math.log10(max(wc, 10)), 0.25, 0.7)
    low_diversity = _clamp((expected_ttr - ttr) / expected_ttr)

    # Component 3: repeated sentence openings.
    repeated = _clamp(metrics["repeated_opening_ratio"] / 0.5)

    score = 0.55 * uniformity + 0.25 * low_diversity + 0.20 * repeated
    return {"score": round(_clamp(score), 4), "available": True, "metrics": metrics}
