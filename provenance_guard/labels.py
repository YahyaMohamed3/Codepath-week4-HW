"""Centralized transparency-label strings.

Every label string lives here exactly once. Route handlers never duplicate these
strings; they call :func:`build_label`.
"""

from __future__ import annotations

from .config import ATTR_LIKELY_AI, ATTR_LIKELY_HUMAN, ATTR_UNCERTAIN

# Label variant identifiers.
VARIANT_AI = "high_confidence_ai"
VARIANT_HUMAN = "high_confidence_human"
VARIANT_UNCERTAIN = "uncertain"

# Verbatim label text. These strings must match planning.md and README.md.
LABEL_TEXT = {
    VARIANT_AI: (
        "Likely AI-generated. Multiple independent signals found patterns "
        "commonly associated with AI-written text. This result is an estimate, "
        "not proof, and the creator may appeal."
    ),
    VARIANT_HUMAN: (
        "Likely human-written. The available signals found more human-like "
        "variation than AI-like patterns. This is an estimate, not a guarantee "
        "of authorship."
    ),
    VARIANT_UNCERTAIN: (
        "Origin uncertain. The signals did not agree strongly enough to "
        "determine whether this content was written by a person or generated "
        "with AI."
    ),
}

SHORT_SAMPLE_SUFFIX = (
    "The submitted sample is too short for a reliable determination."
)

# Certificate label (stretch feature 2). Displayed alongside, never replacing,
# the automated transparency label.
CERTIFICATE_LABEL = (
    "Verified Human Process. The creator completed a time-limited authorship "
    "challenge and supplied draft-process evidence for this submission. This "
    "verification is separate from the automated attribution estimate."
)

_ATTRIBUTION_TO_VARIANT = {
    ATTR_LIKELY_AI: VARIANT_AI,
    ATTR_LIKELY_HUMAN: VARIANT_HUMAN,
    ATTR_UNCERTAIN: VARIANT_UNCERTAIN,
}


def build_label(attribution: str, short_sample: bool = False) -> dict:
    """Return the ``{variant, text}`` transparency label for an attribution.

    When ``short_sample`` is True the short-sample suffix is appended to the
    label text (used when the submission is below the word threshold).
    """
    variant = _ATTRIBUTION_TO_VARIANT.get(attribution, VARIANT_UNCERTAIN)
    text = LABEL_TEXT[variant]
    if short_sample:
        text = f"{text} {SHORT_SAMPLE_SUFFIX}"
    return {"variant": variant, "text": text}
