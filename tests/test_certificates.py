"""Tests for the provenance certificate flow."""

from __future__ import annotations

import sqlite3

SAMPLE = (
    "I built the model of the harbor from memory, plank by plank, over three "
    "winters, checking old photographs when I could and inventing the rest, "
    "because the real harbor had been gone for longer than I had been alive."
)


def _submit(client, creator="creator-1"):
    return client.post(
        "/submit", json={"creator_id": creator, "text": SAMPLE}
    ).get_json()["content_id"]


def _challenge(client, content_id, creator="creator-1"):
    return client.post(
        "/certificate/challenge",
        json={"content_id": content_id, "creator_id": creator},
    )


def _good_response(phrase: str) -> str:
    filler = (
        "I drafted this piece by hand over several evenings, revising the "
        "opening three times and reading it aloud to catch the rhythm before "
        "settling on the final version that you see submitted here today for "
        "review and careful consideration by the system operators and staff. "
        "I kept every intermediate note and outline in a folder, and I am happy "
        "to walk anyone through the messy middle drafts that led here, because "
        "the process really did belong entirely to me from the very beginning."
    )
    return f"{phrase} {filler}"


def test_challenge_creation(client):
    content_id = _submit(client)
    resp = _challenge(client, content_id)
    assert resp.status_code == 201
    data = resp.get_json()
    assert "challenge_id" in data
    assert data["phrase"]
    assert data["expires_at"].endswith("Z")


def test_challenge_creator_mismatch(client):
    content_id = _submit(client, creator="owner")
    resp = _challenge(client, content_id, creator="intruder")
    assert resp.status_code == 403


def test_successful_certificate_and_label(client):
    content_id = _submit(client)
    ch = _challenge(client, content_id).get_json()
    resp = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": content_id,
            "creator_id": "creator-1",
            "challenge_response": _good_response(ch["phrase"]),
            "creator_attestation": True,
            "draft_evidence": ["draft-v1-notes", "draft-v2-outline"],
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "verified"
    assert data["certificate_label"].startswith("Verified Human Process.")

    lookup = client.get(f"/content/{content_id}").get_json()
    assert lookup["certificate"] is not None
    assert lookup["certificate"]["certificate_label"].startswith(
        "Verified Human Process."
    )


def test_insufficient_response_rejected(client):
    content_id = _submit(client)
    ch = _challenge(client, content_id).get_json()
    resp = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": content_id,
            "creator_id": "creator-1",
            "challenge_response": f"{ch['phrase']} too short",
            "creator_attestation": True,
            "draft_evidence": ["a", "b"],
        },
    )
    assert resp.status_code == 400


def test_missing_draft_evidence_rejected(client):
    content_id = _submit(client)
    ch = _challenge(client, content_id).get_json()
    resp = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": content_id,
            "creator_id": "creator-1",
            "challenge_response": _good_response(ch["phrase"]),
            "creator_attestation": True,
            "draft_evidence": ["only-one"],
        },
    )
    assert resp.status_code == 400


def test_missing_phrase_rejected(client):
    content_id = _submit(client)
    ch = _challenge(client, content_id).get_json()
    resp = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": content_id,
            "creator_id": "creator-1",
            "challenge_response": _good_response("some-wrong-phrase-entirely"),
            "creator_attestation": True,
            "draft_evidence": ["a-draft", "b-draft"],
        },
    )
    assert resp.status_code == 400


def test_challenge_cannot_be_reused(client):
    content_id = _submit(client)
    ch = _challenge(client, content_id).get_json()
    body = {
        "challenge_id": ch["challenge_id"],
        "content_id": content_id,
        "creator_id": "creator-1",
        "challenge_response": _good_response(ch["phrase"]),
        "creator_attestation": True,
        "draft_evidence": ["draft-v1", "draft-v2"],
    }
    first = client.post("/certificate/verify", json=body)
    second = client.post("/certificate/verify", json=body)
    assert first.status_code == 201
    assert second.status_code == 409


def test_expired_challenge_rejected(app):
    client = app.test_client()
    content_id = _submit(client)
    ch = _challenge(client, content_id).get_json()

    # Force the challenge to be expired by editing its stored expiry.
    conn = sqlite3.connect(app.config["DATABASE_PATH"])
    conn.execute(
        "UPDATE certificate_challenges SET expires_at = ? WHERE challenge_id = ?",
        ("2000-01-01T00:00:00.000Z", ch["challenge_id"]),
    )
    conn.commit()
    conn.close()

    resp = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": content_id,
            "creator_id": "creator-1",
            "challenge_response": _good_response(ch["phrase"]),
            "creator_attestation": True,
            "draft_evidence": ["draft-v1", "draft-v2"],
        },
    )
    assert resp.status_code == 409


def test_certificate_does_not_erase_active_appeal(client):
    content_id = _submit(client)
    client.post(
        "/appeal",
        json={
            "content_id": content_id,
            "creator_id": "creator-1",
            "creator_reasoning": "I have my full drafting history to share here.",
        },
    )
    ch = _challenge(client, content_id).get_json()
    resp = client.post(
        "/certificate/verify",
        json={
            "challenge_id": ch["challenge_id"],
            "content_id": content_id,
            "creator_id": "creator-1",
            "challenge_response": _good_response(ch["phrase"]),
            "creator_attestation": True,
            "draft_evidence": ["draft-v1", "draft-v2"],
        },
    )
    assert resp.status_code == 201
    # Active appeal (under_review) is preserved, not overwritten by verified.
    assert resp.get_json()["status"] == "under_review"
