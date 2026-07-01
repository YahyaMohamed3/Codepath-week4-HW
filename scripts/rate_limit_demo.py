"""Deterministic rate-limit demonstration.

Uses Flask's test client and a local deterministic detector so it never consumes
Groq credits. The limiter configuration is identical to the real ``/submit``
endpoint (``10 per minute;100 per day``) — only the detector is mocked, so the
demonstration is honest about what it exercises.

Usage:
    python scripts/rate_limit_demo.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from provenance_guard import create_app
from provenance_guard.config import Config


class LocalDetector:
    """Deterministic, offline stand-in for the Groq signal."""

    def analyze(self, text: str) -> dict:
        return {
            "score": 0.5,
            "available": True,
            "reasoning": "local deterministic detector (no API call)",
            "indicators": [],
        }


def main() -> None:
    config = Config(
        groq_api_key=None,
        database_path=os.path.join(
            os.path.dirname(__file__), "..", "rate_limit_demo.db"
        ),
        rate_limits_enabled=True,
    )
    if os.path.exists(config.database_path):
        os.remove(config.database_path)

    app = create_app(config=config, detector=LocalDetector())
    # Reset the shared in-memory limiter so the demo starts from a clean count.
    from provenance_guard.extensions import limiter

    with app.app_context():
        try:
            limiter.reset()
        except Exception:
            pass

    client = app.test_client()
    body = {
        "creator_id": "rate-demo",
        "text": "A sufficiently long passage to pass validation without any API use.",
    }

    accepted, limited, first_429 = 0, 0, None
    for i in range(1, 13):
        resp = client.post("/submit", json=body)
        if resp.status_code == 201:
            accepted += 1
            print(f"  request {i:2d}: 201 accepted")
        elif resp.status_code == 429:
            limited += 1
            if first_429 is None:
                first_429 = resp.get_json()
            print(f"  request {i:2d}: 429 rate-limited")
        else:
            print(f"  request {i:2d}: {resp.status_code} unexpected")

    print(f"\nAccepted: {accepted}   Rate-limited: {limited}")
    print("429 JSON body:")
    print(json.dumps(first_429, indent=2))

    if os.path.exists(config.database_path):
        os.remove(config.database_path)


if __name__ == "__main__":
    main()
