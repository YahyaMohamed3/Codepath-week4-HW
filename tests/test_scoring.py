"""Tests for ensemble scoring and conservative attribution gates."""

from __future__ import annotations

from provenance_guard import scoring
from provenance_guard.config import (
    ATTR_LIKELY_AI,
    ATTR_LIKELY_HUMAN,
    ATTR_UNCERTAIN,
)


def _sig(score, available=True, **extra):
    d = {"score": score, "available": available}
    d.update(extra)
    return d


def _text_signals(llm, stylo, phrase):
    return {
        "llm_semantic": _sig(llm),
        "stylometric": _sig(stylo),
        "phrase_pattern": _sig(phrase),
    }


LONG = 120  # word count above the short-text threshold


def test_strong_ai_agreement_yields_likely_ai():
    signals = _text_signals(0.92, 0.85, 0.88)
    result = scoring.score_text(signals, LONG)
    assert result["attribution"] == ATTR_LIKELY_AI
    assert result["ai_likelihood"] >= 0.80
    assert result["confidence"] >= 0.70


def test_strong_human_agreement_yields_likely_human():
    signals = _text_signals(0.10, 0.15, 0.08)
    result = scoring.score_text(signals, LONG)
    assert result["attribution"] == ATTR_LIKELY_HUMAN
    assert result["ai_likelihood"] <= 0.30


def test_conflicting_signals_are_uncertain_with_penalty():
    # LLM says very AI, local signals say very human -> big disagreement.
    signals = _text_signals(0.95, 0.10, 0.12)
    result = scoring.score_text(signals, LONG)
    assert result["attribution"] == ATTR_UNCERTAIN
    assert result["signal_disagreement"] > 0.5
    assert result["disagreement_penalty"] > 0


def test_disagreement_penalty_capped_at_015():
    signals = _text_signals(1.0, 0.0, 0.0)
    result = scoring.score_text(signals, LONG)
    assert result["disagreement_penalty"] == 0.15


def test_ai_gate_requires_non_llm_corroboration():
    # High LLM + high raw, but both non-LLM signals below 0.60 -> not likely_ai.
    signals = _text_signals(0.95, 0.55, 0.5)
    result = scoring.score_text(signals, LONG)
    assert result["attribution"] != ATTR_LIKELY_AI


def test_ai_gate_requires_llm_threshold():
    # Non-LLM very high but LLM below 0.70 -> conservative, not likely_ai.
    signals = _text_signals(0.65, 0.95, 0.95)
    result = scoring.score_text(signals, LONG)
    assert result["attribution"] != ATTR_LIKELY_AI


def test_human_gate_requires_two_low_signals():
    # raw = .5*.20+.3*.20+.2*.40 = .24 <= 0.30; low signals: llm(.20), stylo(.20) => 2
    signals = _text_signals(0.20, 0.20, 0.40)
    result = scoring.score_text(signals, LONG)
    assert result["attribution"] == ATTR_LIKELY_HUMAN
    # Only one signal <= 0.35 (llm .05); raw still low but corroboration missing.
    signals2 = _text_signals(0.05, 0.45, 0.45)
    r2 = scoring.score_text(signals2, LONG)
    # raw = .025 + .135 + .09 = .25 <= 0.30 but only one low signal -> uncertain.
    assert r2["attribution"] == ATTR_UNCERTAIN


def test_short_text_forced_uncertain_and_capped():
    signals = _text_signals(0.95, 0.9, 0.9)
    result = scoring.score_text(signals, word_count=25)
    assert result["attribution"] == ATTR_UNCERTAIN
    assert result["short_sample"] is True
    assert result["confidence"] <= 0.60


def test_missing_signal_weight_renormalization():
    # LLM unavailable; remaining two signals renormalize to 0.30/0.20 -> 0.6/0.4.
    signals = {
        "llm_semantic": _sig(None, available=False),
        "stylometric": _sig(0.10),
        "phrase_pattern": _sig(0.20),
    }
    result = scoring.score_text(signals, LONG)
    assert result["insufficient_signals"] is False
    # raw = (0.30*0.10 + 0.20*0.20) / 0.50 = 0.14
    assert abs(result["ai_likelihood"] - 0.14) < 1e-6


def test_fewer_than_two_signals_is_insufficient():
    signals = {
        "llm_semantic": _sig(None, available=False),
        "stylometric": _sig(None, available=False),
        "phrase_pattern": _sig(0.5),
    }
    result = scoring.score_text(signals, LONG)
    assert result["insufficient_signals"] is True
    assert result["attribution"] == ATTR_UNCERTAIN


def test_image_scoring_generation_tool_gate():
    signals = {
        "generation_tool": _sig(0.95),
        "metadata_consistency": _sig(0.7),
        "provenance_history": _sig(0.6),
    }
    result = scoring.score_image(signals)
    assert result["attribution"] == ATTR_LIKELY_AI


def test_image_scoring_human_gate():
    signals = {
        "generation_tool": _sig(0.30),
        "metadata_consistency": _sig(0.25),
        "provenance_history": _sig(0.20),
    }
    result = scoring.score_image(signals)
    assert result["attribution"] == ATTR_LIKELY_HUMAN
