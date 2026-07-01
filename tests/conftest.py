"""Shared pytest fixtures.

Every test uses a temporary database and an injected fake detector so the suite
is deterministic and never consumes Groq API credits or touches the developer's
local demo database.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from provenance_guard import create_app  # noqa: E402
from provenance_guard.config import Config  # noqa: E402


class FakeDetector:
    """Deterministic stand-in for the Groq semantic signal.

    ``score`` is the AI-likelihood it always returns. When ``available`` is
    False it mimics an unavailable Groq signal (no invented score).
    """

    def __init__(self, score: float = 0.5, available: bool = True,
                 reasoning: str = "fake reasoning", indicators=None):
        self.score = score
        self.available = available
        self.reasoning = reasoning
        self.indicators = indicators or []
        self.calls = 0

    def analyze(self, text: str) -> dict:
        self.calls += 1
        if not self.available:
            return {
                "score": None,
                "available": False,
                "reasoning": "unavailable",
                "indicators": [],
            }
        return {
            "score": self.score,
            "available": True,
            "reasoning": self.reasoning,
            "indicators": self.indicators,
        }


def make_config(tmp_path, rate_limits=False) -> Config:
    return Config(
        groq_api_key=None,
        database_path=str(tmp_path / "test.db"),
        testing=True,
        rate_limits_enabled=rate_limits,
    )


@pytest.fixture
def fake_detector():
    return FakeDetector(score=0.5)


@pytest.fixture
def make_app(tmp_path):
    """Factory: build an app with a chosen detector and rate-limit setting."""
    def _make(detector=None, rate_limits=False):
        if detector is None:
            detector = FakeDetector(score=0.5)
        config = make_config(tmp_path, rate_limits=rate_limits)
        app = create_app(config=config, detector=detector)
        # The limiter uses a module-level singleton with shared in-memory
        # storage; reset it so rate-limit counters never leak between tests.
        from provenance_guard.extensions import limiter

        with app.app_context():
            try:
                limiter.reset()
            except Exception:
                pass
        return app

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()
