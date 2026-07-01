"""Tests for the structured audit log."""

from __future__ import annotations

SAMPLE = (
    "The lighthouse keeper kept a journal in a hand so small it looked like "
    "lace, recording the weather, the ships, and now and then a line about how "
    "the sea sounded different in October, lower somehow, and more patient."
)


def test_audit_log_has_structured_entries(client):
    # Create several events: two classifications + one appeal.
    ids = []
    for creator in ("a", "b"):
        r = client.post("/submit", json={"creator_id": creator, "text": SAMPLE})
        ids.append(r.get_json()["content_id"])
    client.post(
        "/appeal",
        json={
            "content_id": ids[0],
            "creator_id": "a",
            "creator_reasoning": "This is my own original writing, drafted over a week.",
        },
    )

    events = client.get("/log?limit=50").get_json()["events"]
    assert len(events) >= 3
    # Every event carries attribution, confidence, and a timestamp.
    for e in events:
        assert "attribution" in e
        assert "confidence" in e
        assert e["timestamp"].endswith("Z")


def test_audit_events_newest_first(client):
    client.post("/submit", json={"creator_id": "a", "text": SAMPLE})
    client.post("/submit", json={"creator_id": "b", "text": SAMPLE})
    events = client.get("/log").get_json()["events"]
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps, reverse=True)


def test_audit_never_stores_full_text(client):
    r = client.post("/submit", json={"creator_id": "a", "text": SAMPLE})
    events = client.get("/log").get_json()["events"]
    event = events[0]
    # Preview is capped and the full sample is not present in the audit event.
    assert len(event["preview"]) <= 121
    assert SAMPLE not in event["preview"]
    assert len(event["content_hash"]) == 64  # sha-256 hex


def test_appeal_event_beside_original_classification(client):
    r = client.post("/submit", json={"creator_id": "a", "text": SAMPLE})
    content_id = r.get_json()["content_id"]
    original = r.get_json()
    client.post(
        "/appeal",
        json={
            "content_id": content_id,
            "creator_id": "a",
            "creator_reasoning": "I can show my earlier drafts and research notes.",
        },
    )
    events = client.get("/log").get_json()["events"]
    appeal = next(e for e in events if e["event_type"] == "appeal")
    assert appeal["details"]["original_attribution"] == original["attribution"]
    assert appeal["details"]["original_confidence"] == original["confidence"]
    assert "creator_reasoning" in appeal["details"]
