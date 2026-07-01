"""Tests for the multimodal (image-metadata) submission endpoint."""

from __future__ import annotations

BASE_META = {
    "filename": "artwork.png",
    "mime_type": "image/png",
    "width": 1024,
    "height": 1024,
    "has_exif": False,
    "edit_count": 0,
    "source_hash": "",
    "creator_attestation": False,
    "alt_text": "A surreal city floating above the clouds.",
}


def _post(client, metadata, creator="creator-1"):
    return client.post(
        "/submit/image-metadata",
        json={"creator_id": creator, "metadata": metadata},
    )


def test_valid_image_metadata_returns_common_schema(client):
    resp = _post(client, {**BASE_META, "software": "Photoshop"})
    assert resp.status_code == 201
    data = resp.get_json()
    for key in (
        "content_id",
        "attribution",
        "ai_likelihood",
        "confidence",
        "transparency_label",
        "signals",
        "status",
        "created_at",
    ):
        assert key in data
    assert data["content_type"] == "image_metadata"


def test_individual_image_signals_visible(client):
    data = _post(client, {**BASE_META, "software": "Midjourney"}).get_json()
    signals = data["signals"]
    assert set(signals) == {
        "generation_tool",
        "metadata_consistency",
        "provenance_history",
    }
    for sig in signals.values():
        assert "score" in sig


def test_explicit_generative_tool_scores_high(client):
    data = _post(client, {**BASE_META, "software": "Midjourney"}).get_json()
    assert data["signals"]["generation_tool"]["score"] >= 0.9
    assert data["ai_likelihood"] >= 0.5


def test_stronger_provenance_lowers_ai_likelihood(client):
    weak = _post(client, {**BASE_META, "software": "Photoshop"}).get_json()
    strong = _post(
        client,
        {
            **BASE_META,
            "software": "Photoshop",
            "source_hash": "deadbeef",
            "edit_count": 7,
            "creator_attestation": True,
            "revision_info": "v1,v2,v3",
        },
    ).get_json()
    assert (
        strong["signals"]["provenance_history"]["score"]
        < weak["signals"]["provenance_history"]["score"]
    )
    assert strong["ai_likelihood"] <= weak["ai_likelihood"]


def test_invalid_dimensions_flagged(client):
    data = _post(
        client, {**BASE_META, "width": -5, "height": 0, "software": "Photoshop"}
    ).get_json()
    issues = data["signals"]["metadata_consistency"]["issues"]
    assert any("width" in i for i in issues)
    assert any("height" in i for i in issues)


def test_image_result_persisted_and_audited(client):
    data = _post(client, {**BASE_META, "software": "Midjourney"}).get_json()
    content_id = data["content_id"]
    lookup = client.get(f"/content/{content_id}").get_json()
    assert lookup["content_type"] == "image_metadata"

    events = client.get("/log").get_json()["events"]
    image_events = [e for e in events if e["event_type"] == "image_classification"]
    assert image_events
    assert image_events[0]["content_id"] == content_id


def test_missing_metadata_is_validation_error(client):
    resp = client.post(
        "/submit/image-metadata", json={"creator_id": "c", "metadata": {}}
    )
    assert resp.status_code == 400
