"""Deterministic rate-limit tests (no Groq credits consumed)."""

from __future__ import annotations

SAMPLE = (
    "A short but sufficiently long passage used purely to exercise the rate "
    "limiter without touching any external service or model at all."
)


def test_first_ten_accepted_then_429(make_app):
    app = make_app(rate_limits=True)
    client = app.test_client()

    accepted = 0
    limited = 0
    body = {"creator_id": "rate-tester", "text": SAMPLE}
    for _ in range(12):
        resp = client.post("/submit", json=body)
        if resp.status_code == 201:
            accepted += 1
        elif resp.status_code == 429:
            limited += 1

    assert accepted == 10  # "10 per minute"
    assert limited >= 1


def test_rate_limit_json_error_schema(make_app):
    app = make_app(rate_limits=True)
    client = app.test_client()
    body = {"creator_id": "rate-tester", "text": SAMPLE}
    last = None
    for _ in range(12):
        last = client.post("/submit", json=body)
    assert last.status_code == 429
    data = last.get_json()
    assert data["error"] == "rate_limit_exceeded"
    assert data["message"] == "Too many requests. Please wait before trying again."
