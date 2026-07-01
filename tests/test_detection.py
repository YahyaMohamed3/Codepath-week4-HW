"""Tests for the individual detection signals."""

from __future__ import annotations

import pytest

from provenance_guard.detection import (
    image_metadata_signal,
    llm_signal,
    phrase_signal,
    stylometric_signal,
)


# --- Groq semantic signal ---------------------------------------------------
def test_groq_parse_valid_json():
    raw = '{"ai_likelihood": 0.83, "reasoning": "uniform tone", "indicators": ["a"]}'
    result = llm_signal.parse_response(raw)
    assert result["available"] is True
    assert result["score"] == 0.83
    assert result["indicators"] == ["a"]


def test_groq_parse_json_embedded_in_text():
    raw = 'Here is the result: {"ai_likelihood": 1.5, "reasoning": "x"} thanks'
    result = llm_signal.parse_response(raw)
    # Score is clamped into [0, 1].
    assert result["score"] == 1.0


def test_groq_malformed_output_raises():
    with pytest.raises(ValueError):
        llm_signal.parse_response("not json at all")
    with pytest.raises(ValueError):
        llm_signal.parse_response('{"reasoning": "missing score"}')


def test_groq_unavailable_when_no_key_or_client():
    signal = llm_signal.GroqSemanticSignal(api_key=None, client=None)
    result = signal.analyze("some text to analyze here")
    assert result["available"] is False
    assert result["score"] is None


def test_groq_uses_injected_client_and_handles_failure():
    class BoomClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("network down")

    signal = llm_signal.GroqSemanticSignal(client=BoomClient())
    result = signal.analyze("text")
    # External failure is translated safely, never a random score.
    assert result["available"] is False
    assert result["score"] is None


def test_groq_injected_client_success():
    class FakeMessage:
        content = '{"ai_likelihood": 0.4, "reasoning": "ok", "indicators": []}'

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeCompletion()

    signal = llm_signal.GroqSemanticSignal(client=FakeClient())
    result = signal.analyze("text")
    assert result["available"] is True
    assert result["score"] == 0.4


# --- Stylometric signal -----------------------------------------------------
def test_stylometric_returns_metrics_and_score():
    text = (
        "The system works well. Users appreciate the clarity. "
        "However, some prefer more detail, especially in edge cases where the "
        "behavior is subtle and occasionally surprising. Short works too."
    )
    result = stylometric_signal.analyze(text)
    assert result["available"] is True
    assert 0.0 <= result["score"] <= 1.0
    metrics = result["metrics"]
    assert metrics["word_count"] > 0
    assert metrics["sentence_count"] >= 3
    assert "type_token_ratio" in metrics
    assert "sentence_length_cv" in metrics


def test_stylometric_uniform_more_ai_than_varied():
    uniform = " ".join(["The cat sat on the mat today." for _ in range(6)])
    varied = (
        "Rain. It fell for days without pause, soaking everything. "
        "Then, suddenly, the sky cleared and a brilliant warmth returned to the "
        "long, quiet valley below the ridge. People smiled again."
    )
    assert stylometric_signal.analyze(uniform)["score"] >= (
        stylometric_signal.analyze(varied)["score"]
    )


def test_stylometric_no_division_by_zero_on_empty():
    result = stylometric_signal.analyze("")
    assert result["metrics"]["word_count"] == 0
    assert 0.0 <= result["score"] <= 1.0


# --- Phrase signal ----------------------------------------------------------
def test_phrase_single_match_is_not_high():
    text = (
        "Furthermore, the weather was pleasant and we walked along the river "
        "for a long while enjoying the quiet afternoon and the cool breeze."
    )
    result = phrase_signal.analyze(text)
    assert result["score"] < 0.3  # a single formulaic phrase is weak evidence


def test_phrase_multiple_matches_raise_score():
    text = (
        "It is important to note that this topic is multifaceted. Furthermore, "
        "it plays a crucial role in modern life. In conclusion, we must delve "
        "into the realm of possibilities and foster a better future."
    )
    result = phrase_signal.analyze(text)
    assert result["score"] > 0.4
    assert len(result["matches"]) >= 3


def test_phrase_empty_text():
    result = phrase_signal.analyze("")
    assert result["score"] == 0.0
    assert result["matches"] == []


# --- Image metadata signals -------------------------------------------------
def test_image_generation_tool_marker_high():
    result = image_metadata_signal.generation_tool_signal({"software": "Midjourney"})
    assert result["score"] >= 0.9
    assert "midjourney" in result["matched_tools"]


def test_image_editing_software_not_flagged_as_ai():
    result = image_metadata_signal.generation_tool_signal({"software": "Photoshop"})
    assert result["score"] < 0.5
    assert result["matched_tools"] == []


def test_image_consistency_flags_mime_mismatch():
    result = image_metadata_signal.metadata_consistency_signal(
        {"filename": "art.png", "mime_type": "image/jpeg", "width": 10, "height": 10}
    )
    assert "mime/extension mismatch" in result["issues"]


def test_image_provenance_evidence_lowers_score():
    strong = image_metadata_signal.provenance_history_signal(
        {"source_hash": "abc", "edit_count": 5, "creator_attestation": True,
         "revision_info": "v1,v2"}
    )
    weak = image_metadata_signal.provenance_history_signal({})
    assert strong["score"] < weak["score"]
