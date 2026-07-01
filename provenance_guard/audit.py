"""Structured audit logging.

Audit events never store full private text. For each event we store a SHA-256
content hash, character/word counts, and a short preview (<=120 chars), plus a
structured JSON details blob. Every classification event carries the attribution,
confidence, AI likelihood, individual signal scores, status, and timestamp.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from .database import utcnow_iso

# Event type identifiers.
EVENT_CLASSIFICATION = "classification"
EVENT_IMAGE_CLASSIFICATION = "image_classification"
EVENT_APPEAL = "appeal"
EVENT_CERTIFICATE = "certificate"

PREVIEW_MAX_CHARS = 120


def content_hash(text: str) -> str:
    """Return the SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_preview(text: str) -> str:
    """Return a whitespace-normalized preview of at most 120 characters."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= PREVIEW_MAX_CHARS:
        return collapsed
    return collapsed[: PREVIEW_MAX_CHARS - 1] + "…"


def signal_scores(signals: dict) -> dict:
    """Extract just the ``{name: score}`` map from a full signals dict."""
    return {name: sig.get("score") for name, sig in signals.items()}


def write_audit_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    content_id: str | None,
    creator_id: str | None,
    content_type: str | None,
    attribution: str | None,
    confidence: float | None,
    ai_likelihood: float | None,
    signals: dict | None,
    status: str | None,
    content_hash_value: str | None,
    preview: str | None,
    details: dict,
) -> str:
    """Insert a structured audit event using the provided connection.

    The caller is responsible for the surrounding transaction (commit) so audit
    writes can be atomic with the primary record they describe.
    """
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO audit_events (
            event_id, event_type, timestamp, content_id, creator_id,
            content_type, attribution, confidence, ai_likelihood, signals_json,
            status, content_hash, preview, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            utcnow_iso(),
            content_id,
            creator_id,
            content_type,
            attribution,
            confidence,
            ai_likelihood,
            json.dumps(signal_scores(signals)) if signals is not None else None,
            status,
            content_hash_value,
            preview,
            json.dumps(details),
        ),
    )
    return event_id


def row_to_event(row: sqlite3.Row) -> dict:
    """Convert an ``audit_events`` row into a JSON-serializable dict."""
    return {
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "timestamp": row["timestamp"],
        "content_id": row["content_id"],
        "creator_id": row["creator_id"],
        "content_type": row["content_type"],
        "attribution": row["attribution"],
        "confidence": row["confidence"],
        "ai_likelihood": row["ai_likelihood"],
        "signals": json.loads(row["signals_json"]) if row["signals_json"] else None,
        "status": row["status"],
        "content_hash": row["content_hash"],
        "preview": row["preview"],
        "details": json.loads(row["details_json"]) if row["details_json"] else {},
    }
