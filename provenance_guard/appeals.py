"""Appeals service.

A creator may appeal an automated classification. The original classification is
never overwritten; instead an appeal record is created, the submission status is
flipped to ``under_review``, and a structured audit event captures the original
attribution/confidence alongside the creator's reasoning. Duplicate appeals are
idempotent.
"""

from __future__ import annotations

import sqlite3
import uuid

from . import audit
from .config import APPEAL_MIN_REASONING_CHARS, STATUS_UNDER_REVIEW
from .database import utcnow_iso
from .errors import forbidden, not_found, validation_error


def _existing_appeal(conn: sqlite3.Connection, content_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM appeals WHERE content_id = ?", (content_id,)
    ).fetchone()


def submit_appeal(
    conn: sqlite3.Connection,
    *,
    content_id: str,
    creator_id: str,
    creator_reasoning: str,
) -> dict:
    """Create (or return an existing) appeal for a submission.

    Raises :class:`APIError` for validation, ownership, and lookup failures.
    """
    if not isinstance(creator_reasoning, str) or (
        len(creator_reasoning.strip()) < APPEAL_MIN_REASONING_CHARS
    ):
        raise validation_error(
            "The creator_reasoning field must contain at least "
            f"{APPEAL_MIN_REASONING_CHARS} characters.",
            {"field": "creator_reasoning"},
        )

    submission = conn.execute(
        "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
    ).fetchone()
    if submission is None:
        raise not_found(
            "No submission was found for that content_id.",
            {"content_id": content_id},
        )

    if submission["creator_id"] != creator_id:
        raise forbidden(
            "This creator_id does not match the creator on the submission."
        )

    # Idempotent: a second appeal returns the first rather than duplicating.
    existing = _existing_appeal(conn, content_id)
    if existing is not None:
        return {
            "appeal_id": existing["appeal_id"],
            "content_id": content_id,
            "status": existing["status"],
            "creator_reasoning": existing["creator_reasoning"],
            "submitted_at": existing["submitted_at"],
            "message": "An appeal already exists for this content and is under review.",
            "duplicate": True,
        }

    appeal_id = str(uuid.uuid4())
    submitted_at = utcnow_iso()

    # Transaction: create appeal, update status, write audit event atomically.
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO appeals (
                appeal_id, content_id, creator_id, creator_reasoning, status,
                original_attribution, original_confidence,
                original_ai_likelihood, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                appeal_id,
                content_id,
                creator_id,
                creator_reasoning.strip(),
                STATUS_UNDER_REVIEW,
                submission["attribution"],
                submission["confidence"],
                submission["ai_likelihood"],
                submitted_at,
            ),
        )
        conn.execute(
            "UPDATE submissions SET status = ? WHERE content_id = ?",
            (STATUS_UNDER_REVIEW, content_id),
        )
        audit.write_audit_event(
            conn,
            event_type=audit.EVENT_APPEAL,
            content_id=content_id,
            creator_id=creator_id,
            content_type=submission["content_type"],
            # Preserve the original classification in the audit trail.
            attribution=submission["attribution"],
            confidence=submission["confidence"],
            ai_likelihood=submission["ai_likelihood"],
            signals=None,
            status=STATUS_UNDER_REVIEW,
            content_hash_value=submission["content_hash"],
            preview=submission["preview"],
            details={
                "creator_reasoning": creator_reasoning.strip(),
                "original_attribution": submission["attribution"],
                "original_confidence": submission["confidence"],
                "original_ai_likelihood": submission["ai_likelihood"],
                "new_status": STATUS_UNDER_REVIEW,
            },
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "appeal_id": appeal_id,
        "content_id": content_id,
        "status": STATUS_UNDER_REVIEW,
        "creator_reasoning": creator_reasoning.strip(),
        "submitted_at": submitted_at,
        "message": "Your appeal was received and the content is now under review.",
        "duplicate": False,
    }
