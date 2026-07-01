"""Provenance certificate service (stretch feature 2).

This does NOT prove human authorship mathematically. It verifies that a creator
completed a time-limited, creator-controlled process: they responded to a
freshly issued challenge phrase, wrote a substantive process note, explicitly
attested, and supplied draft-process evidence. The resulting certificate is
displayed *alongside* — never replacing — the automated transparency label.
"""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import datetime, timezone

from . import audit
from .config import (
    CERTIFICATE_CHALLENGE_TTL_SECONDS,
    CERTIFICATE_MIN_DRAFT_EVIDENCE,
    CERTIFICATE_MIN_RESPONSE_WORDS,
    STATUS_UNDER_REVIEW,
    STATUS_VERIFIED,
)
from .database import utcnow_iso
from .errors import conflict, forbidden, not_found, validation_error
from .labels import CERTIFICATE_LABEL

# Small wordlist for human-friendly challenge phrases (no ambiguous words).
_PHRASE_WORDS = [
    "amber", "harbor", "lantern", "meadow", "compass", "cedar", "ripple",
    "orbit", "willow", "quartz", "beacon", "thistle", "marble", "cobalt",
    "juniper", "saffron", "velvet", "ember", "granite", "lattice",
]


def _parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )


def _generate_phrase() -> str:
    words = [secrets.choice(_PHRASE_WORDS) for _ in range(3)]
    return "-".join(words)


def _load_submission(conn: sqlite3.Connection, content_id: str) -> sqlite3.Row:
    submission = conn.execute(
        "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
    ).fetchone()
    if submission is None:
        raise not_found(
            "No submission was found for that content_id.",
            {"content_id": content_id},
        )
    return submission


def create_challenge(
    conn: sqlite3.Connection, *, content_id: str, creator_id: str
) -> dict:
    """Create a time-limited authorship challenge for a submission."""
    submission = _load_submission(conn, content_id)
    if submission["creator_id"] != creator_id:
        raise forbidden(
            "This creator_id does not match the creator on the submission."
        )

    challenge_id = str(uuid.uuid4())
    phrase = _generate_phrase()
    created = datetime.now(timezone.utc)
    created_at = utcnow_iso()
    expires_dt = created.timestamp() + CERTIFICATE_CHALLENGE_TTL_SECONDS
    expires_at = (
        datetime.fromtimestamp(expires_dt, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )

    conn.execute(
        """
        INSERT INTO certificate_challenges (
            challenge_id, content_id, creator_id, phrase, created_at,
            expires_at, used
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (challenge_id, content_id, creator_id, phrase, created_at, expires_at),
    )
    conn.commit()

    return {
        "challenge_id": challenge_id,
        "content_id": content_id,
        "phrase": phrase,
        "expires_at": expires_at,
        "instructions": (
            "Within 10 minutes, submit a process note of at least "
            f"{CERTIFICATE_MIN_RESPONSE_WORDS} words that includes the exact "
            "phrase above, set creator_attestation to true, and provide at "
            f"least {CERTIFICATE_MIN_DRAFT_EVIDENCE} draft-evidence entries."
        ),
    }


def verify_challenge(
    conn: sqlite3.Connection,
    *,
    challenge_id: str,
    content_id: str,
    creator_id: str,
    challenge_response: str,
    creator_attestation: bool,
    draft_evidence: list,
) -> dict:
    """Verify a challenge response and issue a certificate on success."""
    submission = _load_submission(conn, content_id)
    if submission["creator_id"] != creator_id:
        raise forbidden(
            "This creator_id does not match the creator on the submission."
        )

    challenge = conn.execute(
        "SELECT * FROM certificate_challenges WHERE challenge_id = ?",
        (challenge_id,),
    ).fetchone()
    if challenge is None:
        raise not_found(
            "No challenge was found for that challenge_id.",
            {"challenge_id": challenge_id},
        )
    if challenge["content_id"] != content_id or challenge["creator_id"] != creator_id:
        raise forbidden("The challenge does not belong to this creator/content.")
    if challenge["used"]:
        raise conflict("This challenge has already been used.")
    if datetime.now(timezone.utc) > _parse_iso(challenge["expires_at"]):
        raise conflict("This challenge has expired. Request a new one.")

    # Validate the process evidence.
    response_text = challenge_response if isinstance(challenge_response, str) else ""
    if challenge["phrase"].lower() not in response_text.lower():
        raise validation_error(
            "The challenge response must include the exact challenge phrase.",
            {"field": "challenge_response"},
        )
    word_count = len(response_text.split())
    if word_count < CERTIFICATE_MIN_RESPONSE_WORDS:
        raise validation_error(
            "The challenge response must contain at least "
            f"{CERTIFICATE_MIN_RESPONSE_WORDS} words.",
            {"field": "challenge_response", "word_count": word_count},
        )
    if creator_attestation is not True:
        raise validation_error(
            "Explicit creator_attestation (true) is required.",
            {"field": "creator_attestation"},
        )
    evidence = [
        str(e).strip()
        for e in (draft_evidence or [])
        if isinstance(e, (str, int, float)) and str(e).strip()
    ]
    if len(evidence) < CERTIFICATE_MIN_DRAFT_EVIDENCE:
        raise validation_error(
            "At least "
            f"{CERTIFICATE_MIN_DRAFT_EVIDENCE} non-empty draft_evidence entries "
            "are required.",
            {"field": "draft_evidence"},
        )

    certificate_id = str(uuid.uuid4())
    issued_at = utcnow_iso()
    evidence_summary = "; ".join(evidence[:10])

    # Do not erase an active appeal: only promote to verified if not under review.
    current_status = submission["status"]
    new_status = (
        current_status if current_status == STATUS_UNDER_REVIEW else STATUS_VERIFIED
    )

    try:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE certificate_challenges SET used = 1 WHERE challenge_id = ?",
            (challenge_id,),
        )
        conn.execute(
            """
            INSERT INTO certificates (
                certificate_id, content_id, creator_id, challenge_id,
                evidence_summary, issued_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                certificate_id,
                content_id,
                creator_id,
                challenge_id,
                evidence_summary,
                issued_at,
            ),
        )
        conn.execute(
            "UPDATE submissions SET status = ? WHERE content_id = ?",
            (new_status, content_id),
        )
        audit.write_audit_event(
            conn,
            event_type=audit.EVENT_CERTIFICATE,
            content_id=content_id,
            creator_id=creator_id,
            content_type=submission["content_type"],
            attribution=submission["attribution"],
            confidence=submission["confidence"],
            ai_likelihood=submission["ai_likelihood"],
            signals=None,
            status=new_status,
            content_hash_value=submission["content_hash"],
            preview=submission["preview"],
            details={
                "certificate_id": certificate_id,
                "challenge_id": challenge_id,
                "evidence_count": len(evidence),
                "evidence_summary": evidence_summary,
                "response_word_count": word_count,
            },
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "certificate_id": certificate_id,
        "content_id": content_id,
        "status": new_status,
        "issued_at": issued_at,
        "evidence_summary": evidence_summary,
        "certificate_label": CERTIFICATE_LABEL,
        "message": "Certificate issued. Verified human-process evidence recorded.",
    }


def certificate_for_content(conn: sqlite3.Connection, content_id: str) -> dict | None:
    """Return the most recent certificate for a submission, if any."""
    row = conn.execute(
        "SELECT * FROM certificates WHERE content_id = ? ORDER BY issued_at DESC",
        (content_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "certificate_id": row["certificate_id"],
        "content_id": row["content_id"],
        "issued_at": row["issued_at"],
        "evidence_summary": row["evidence_summary"],
        "certificate_label": CERTIFICATE_LABEL,
    }
