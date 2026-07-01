"""Ensemble scoring and conservative attribution logic.

All signal scores are estimated AI likelihoods in ``[0, 1]``. This module
combines them with fixed weights, applies a disagreement penalty to confidence,
and converts the numbers into a conservative attribution that favors avoiding
false positives against human writers.
"""

from __future__ import annotations

from .config import (
    AI_CONFIDENCE_MIN,
    AI_LLM_MIN,
    AI_NON_LLM_MIN,
    AI_RAW_MIN,
    ATTR_LIKELY_AI,
    ATTR_LIKELY_HUMAN,
    ATTR_UNCERTAIN,
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    HUMAN_CONFIDENCE_MIN,
    HUMAN_RAW_MAX,
    HUMAN_SIGNAL_MAX,
    IMAGE_WEIGHTS,
    SHORT_TEXT_CONFIDENCE_CAP,
    SHORT_TEXT_WORD_THRESHOLD,
    TEXT_WEIGHTS,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _available(signals: dict, weights: dict) -> dict[str, float]:
    """Return ``{name: score}`` for signals that are available and weighted."""
    return {
        name: float(sig["score"])
        for name, sig in signals.items()
        if name in weights and sig.get("available") and sig.get("score") is not None
    }


def _ensemble_core(available: dict[str, float], weights: dict) -> dict:
    """Compute raw likelihood, disagreement, and confidence for the ensemble.

    Weights are re-normalized across only the available signals.
    """
    total_weight = sum(weights[name] for name in available)
    raw = sum(weights[name] * score for name, score in available.items())
    raw = raw / total_weight if total_weight else 0.0

    scores = list(available.values())
    disagreement = (max(scores) - min(scores)) if len(scores) > 1 else 0.0
    penalty = min(0.15, disagreement * 0.20)
    base_certainty = max(raw, 1.0 - raw)
    confidence = _clamp(
        base_certainty - penalty, CONFIDENCE_FLOOR, CONFIDENCE_CEILING
    )
    return {
        "raw_ai_likelihood": round(raw, 4),
        "signal_disagreement": round(disagreement, 4),
        "disagreement_penalty": round(penalty, 4),
        "confidence": round(confidence, 4),
    }


def score_text(signals: dict, word_count: int) -> dict:
    """Combine the three text signals into an attribution result.

    Returns a dict with ``attribution``, ``ai_likelihood``, ``confidence``,
    ``signal_disagreement``, ``short_sample``, and ``insufficient_signals``.
    """
    available = _available(signals, TEXT_WEIGHTS)

    # Fewer than two signals: we cannot combine meaningfully.
    if len(available) < 2:
        return {
            "attribution": ATTR_UNCERTAIN,
            "ai_likelihood": None,
            "confidence": CONFIDENCE_FLOOR,
            "signal_disagreement": 0.0,
            "disagreement_penalty": 0.0,
            "short_sample": word_count < SHORT_TEXT_WORD_THRESHOLD,
            "insufficient_signals": True,
        }

    core = _ensemble_core(available, TEXT_WEIGHTS)
    raw = core["raw_ai_likelihood"]
    confidence = core["confidence"]

    # Short text: not enough evidence for a reliable determination.
    if word_count < SHORT_TEXT_WORD_THRESHOLD:
        return {
            "attribution": ATTR_UNCERTAIN,
            "ai_likelihood": raw,
            "confidence": min(confidence, SHORT_TEXT_CONFIDENCE_CAP),
            "signal_disagreement": core["signal_disagreement"],
            "disagreement_penalty": core["disagreement_penalty"],
            "short_sample": True,
            "insufficient_signals": False,
        }

    attribution = _attribute_text(available, raw, confidence)

    return {
        "attribution": attribution,
        "ai_likelihood": raw,
        "confidence": confidence,
        "signal_disagreement": core["signal_disagreement"],
        "disagreement_penalty": core["disagreement_penalty"],
        "short_sample": False,
        "insufficient_signals": False,
    }


def _attribute_text(available: dict[str, float], raw: float, confidence: float) -> str:
    """Apply the conservative text decision gates."""
    llm = available.get("llm_semantic")
    non_llm = [
        score for name, score in available.items() if name != "llm_semantic"
    ]

    # likely_ai requires strong, corroborated evidence.
    if (
        raw >= AI_RAW_MIN
        and confidence >= AI_CONFIDENCE_MIN
        and llm is not None
        and llm >= AI_LLM_MIN
        and any(score >= AI_NON_LLM_MIN for score in non_llm)
    ):
        return ATTR_LIKELY_AI

    # likely_human requires low likelihood and at least two low signals.
    low_signals = [s for s in available.values() if s <= HUMAN_SIGNAL_MAX]
    if (
        raw <= HUMAN_RAW_MAX
        and confidence >= HUMAN_CONFIDENCE_MIN
        and len(low_signals) >= 2
    ):
        return ATTR_LIKELY_HUMAN

    return ATTR_UNCERTAIN


def score_image(signals: dict) -> dict:
    """Combine the three image-metadata signals into an attribution result."""
    available = _available(signals, IMAGE_WEIGHTS)

    if len(available) < 2:
        return {
            "attribution": ATTR_UNCERTAIN,
            "ai_likelihood": None,
            "confidence": CONFIDENCE_FLOOR,
            "signal_disagreement": 0.0,
            "disagreement_penalty": 0.0,
            "short_sample": False,
            "insufficient_signals": True,
        }

    core = _ensemble_core(available, IMAGE_WEIGHTS)
    raw = core["raw_ai_likelihood"]
    confidence = core["confidence"]
    attribution = _attribute_image(available, raw, confidence)

    return {
        "attribution": attribution,
        "ai_likelihood": raw,
        "confidence": confidence,
        "signal_disagreement": core["signal_disagreement"],
        "disagreement_penalty": core["disagreement_penalty"],
        "short_sample": False,
        "insufficient_signals": False,
    }


def _attribute_image(available: dict[str, float], raw: float, confidence: float) -> str:
    """Conservative image gates: an explicit tool marker is the strong signal."""
    gen_tool = available.get("generation_tool", 0.0)
    provenance = available.get("provenance_history", 1.0)

    if (
        raw >= AI_RAW_MIN
        and confidence >= AI_CONFIDENCE_MIN
        and gen_tool >= AI_LLM_MIN
    ):
        return ATTR_LIKELY_AI

    low_signals = [s for s in available.values() if s <= HUMAN_SIGNAL_MAX]
    if (
        raw <= HUMAN_RAW_MAX
        and confidence >= HUMAN_CONFIDENCE_MIN
        and len(low_signals) >= 2
        and provenance <= HUMAN_SIGNAL_MAX
    ):
        return ATTR_LIKELY_HUMAN

    return ATTR_UNCERTAIN
