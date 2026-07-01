"""Centralized configuration for Provenance Guard.

All tunable constants (weights, thresholds, limits, model name) live here so the
rest of the codebase never hard-codes a magic number in a route handler.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Attribution values and content statuses (used consistently across the app).
# ---------------------------------------------------------------------------
ATTR_LIKELY_AI = "likely_ai"
ATTR_LIKELY_HUMAN = "likely_human"
ATTR_UNCERTAIN = "uncertain"

STATUS_CLASSIFIED = "classified"
STATUS_UNDER_REVIEW = "under_review"
STATUS_VERIFIED = "verified"

CONTENT_TYPE_TEXT = "text"
CONTENT_TYPE_IMAGE = "image_metadata"

# Groq model used for the semantic signal.
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# Text validation bounds.
TEXT_MIN_CHARS = 20
TEXT_MAX_CHARS = 10_000
APPEAL_MIN_REASONING_CHARS = 20

# Short-text handling.
SHORT_TEXT_WORD_THRESHOLD = 40
SHORT_TEXT_CONFIDENCE_CAP = 0.60

# Ensemble weights for text signals.
TEXT_WEIGHTS = {
    "llm_semantic": 0.50,
    "stylometric": 0.30,
    "phrase_pattern": 0.20,
}

# Ensemble weights for image-metadata signals.
IMAGE_WEIGHTS = {
    "generation_tool": 0.50,
    "metadata_consistency": 0.25,
    "provenance_history": 0.25,
}

# Confidence bounds.
CONFIDENCE_FLOOR = 0.50
CONFIDENCE_CEILING = 0.99

# Conservative decision gates for text.
AI_RAW_MIN = 0.80
AI_CONFIDENCE_MIN = 0.70
AI_LLM_MIN = 0.70
AI_NON_LLM_MIN = 0.60

HUMAN_RAW_MAX = 0.30
HUMAN_CONFIDENCE_MIN = 0.70
HUMAN_SIGNAL_MAX = 0.35

# Certificate challenge lifetime.
CERTIFICATE_CHALLENGE_TTL_SECONDS = 10 * 60
CERTIFICATE_MIN_RESPONSE_WORDS = 50
CERTIFICATE_MIN_DRAFT_EVIDENCE = 2

# Rate limits (used by Flask-Limiter).
RATE_LIMIT_SUBMIT = "10 per minute;100 per day"
RATE_LIMIT_IMAGE = "10 per minute;100 per day"
RATE_LIMIT_APPEAL = "5 per hour"
RATE_LIMIT_CERTIFICATE = "5 per hour"


@dataclass
class Config:
    """Application configuration resolved from the environment."""

    groq_api_key: str | None = field(
        default_factory=lambda: os.environ.get("GROQ_API_KEY")
    )
    groq_model: str = field(
        default_factory=lambda: os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    )
    database_path: str = field(
        default_factory=lambda: os.environ.get(
            "PROVENANCE_DB_PATH", "provenance_guard.db"
        )
    )
    secret_key: str = field(
        default_factory=lambda: os.environ.get("SECRET_KEY", "dev-secret-key")
    )
    # When True, routes skip the real Groq call and use an injected detector.
    # Tests set this so they never consume API credits.
    testing: bool = False
    rate_limits_enabled: bool = True

    @property
    def groq_configured(self) -> bool:
        """Whether a Groq API key is present (without exposing the key)."""
        return bool(self.groq_api_key)
