"""Tests for the analytics endpoint."""

from __future__ import annotations

SAMPLE = (
    "We spent the whole afternoon fixing the fence, and by evening my hands "
    "were sore and my mind was quiet in a way it had not been for months, the "
    "small honest labor having pushed everything else out to the edges."
)


def test_empty_database_no_division_error(client):
    data = client.get("/analytics").get_json()
    assert data["total_submissions"] == 0
    assert data["appeal_rate"] == 0.0
    assert data["average_confidence"] == 0.0
    assert data["likely_ai_ratio"] == 0.0


def test_distribution_and_counts(client):
    for creator in ("a", "b", "c"):
        client.post("/submit", json={"creator_id": creator, "text": SAMPLE})
    data = client.get("/analytics").get_json()
    assert data["total_submissions"] == 3
    assert data["text_submissions"] == 3
    total_attr = (
        data["likely_ai_count"]
        + data["likely_human_count"]
        + data["uncertain_count"]
    )
    assert total_attr == 3
    ratios = (
        data["likely_ai_ratio"]
        + data["likely_human_ratio"]
        + data["uncertain_ratio"]
    )
    assert abs(ratios - 1.0) < 1e-6


def test_appeal_rate_and_certificate_count(client):
    cid = client.post(
        "/submit", json={"creator_id": "a", "text": SAMPLE}
    ).get_json()["content_id"]
    client.post("/submit", json={"creator_id": "b", "text": SAMPLE})
    client.post(
        "/appeal",
        json={
            "content_id": cid,
            "creator_id": "a",
            "creator_reasoning": "This is entirely my own writing and I can prove it.",
        },
    )
    data = client.get("/analytics").get_json()
    assert data["appeal_count"] == 1
    assert data["appeal_rate"] == round(1 / 2, 4)
    assert data["certificate_count"] == 0
    assert data["under_review_count"] == 1


def test_average_confidence_present(client):
    client.post("/submit", json={"creator_id": "a", "text": SAMPLE})
    data = client.get("/analytics").get_json()
    assert 0.0 < data["average_confidence"] <= 1.0


def test_dashboard_renders(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Attribution distribution" in resp.data
    assert b"Appeal rate" in resp.data
