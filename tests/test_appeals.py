"""Tests for the appeals workflow."""

from __future__ import annotations

SAMPLE = (
    "The garden had gone wild in the years since anyone tended it, roses "
    "climbing over the broken fence and mint spreading everywhere it pleased. "
    "I liked it better that way, honestly, unruly and alive and entirely its "
    "own thing, indifferent to whatever plans we had once made for it."
)
REASONING = "I wrote this from my own experience and can provide earlier drafts."


def _submit(client, creator="creator-1"):
    resp = client.post("/submit", json={"creator_id": creator, "text": SAMPLE})
    return resp.get_json()["content_id"]


def test_successful_appeal_sets_under_review(client):
    content_id = _submit(client)
    resp = client.post(
        "/appeal",
        json={
            "content_id": content_id,
            "creator_id": "creator-1",
            "creator_reasoning": REASONING,
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "under_review"
    assert data["content_id"] == content_id

    lookup = client.get(f"/content/{content_id}").get_json()
    assert lookup["status"] == "under_review"
    # Original classification is preserved, not overwritten.
    assert lookup["attribution"] in ("likely_ai", "likely_human", "uncertain")


def test_appeal_reasoning_visible_in_log(client):
    content_id = _submit(client)
    client.post(
        "/appeal",
        json={
            "content_id": content_id,
            "creator_id": "creator-1",
            "creator_reasoning": REASONING,
        },
    )
    log = client.get("/log").get_json()["events"]
    appeal_events = [e for e in log if e["event_type"] == "appeal"]
    assert appeal_events
    event = appeal_events[0]
    assert event["details"]["creator_reasoning"] == REASONING
    # Original attribution + confidence retained alongside the appeal.
    assert "original_attribution" in event["details"]
    assert event["attribution"] is not None
    assert event["confidence"] is not None


def test_appeal_creator_mismatch_is_403(client):
    content_id = _submit(client, creator="owner")
    resp = client.post(
        "/appeal",
        json={
            "content_id": content_id,
            "creator_id": "someone-else",
            "creator_reasoning": REASONING,
        },
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_appeal_unknown_content_is_404(client):
    resp = client.post(
        "/appeal",
        json={
            "content_id": "nope",
            "creator_id": "creator-1",
            "creator_reasoning": REASONING,
        },
    )
    assert resp.status_code == 404


def test_appeal_short_reasoning_is_400(client):
    content_id = _submit(client)
    resp = client.post(
        "/appeal",
        json={
            "content_id": content_id,
            "creator_id": "creator-1",
            "creator_reasoning": "too short",
        },
    )
    assert resp.status_code == 400


def test_duplicate_appeal_returns_existing(client):
    content_id = _submit(client)
    body = {
        "content_id": content_id,
        "creator_id": "creator-1",
        "creator_reasoning": REASONING,
    }
    first = client.post("/appeal", json=body)
    second = client.post("/appeal", json=body)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["appeal_id"] == first.get_json()["appeal_id"]
    assert second.get_json()["duplicate"] is True
