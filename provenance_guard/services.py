"""Classification pipeline services.

Ties detection signals, ensemble scoring, persistence, and audit logging into two
operations: classify text and classify image metadata. Routes stay thin by
delegating here.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid

from . import audit, scoring
from .config import CONTENT_TYPE_IMAGE, CONTENT_TYPE_TEXT, STATUS_CLASSIFIED
from .database import utcnow_iso
from .detection import phrase_signal, stylometric_signal
from .errors import service_unavailable
from .labels import build_label

_WORD_RE = re.compile(r"[A-Za-z']+|\d+")


def _word_count(text: str) -> int:
    return len(text.split())


def _persist(
    conn: sqlite3.Connection,
    *,
    record: dict,
    full_text: str | None,
    metadata: dict | None,
    event_type: str,
) -> None:
    """Persist a submission and its audit event in a single transaction."""
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO submissions (
                content_id, creator_id, content_type, attribution,
                ai_likelihood, confidence, signal_disagreement, status,
                label_variant, label_text, signals_json, content_hash,
                char_count, word_count, preview, full_text, metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["content_id"],
                record["creator_id"],
                record["content_type"],
                record["attribution"],
                record["ai_likelihood"],
                record["confidence"],
                record["signal_disagreement"],
                record["status"],
                record["transparency_label"]["variant"],
                record["transparency_label"]["text"],
                json.dumps(record["signals"]),
                record["_content_hash"],
                record["_char_count"],
                record["_word_count"],
                record["_preview"],
                full_text,
                json.dumps(metadata) if metadata is not None else None,
                record["created_at"],
            ),
        )
        audit.write_audit_event(
            conn,
            event_type=event_type,
            content_id=record["content_id"],
            creator_id=record["creator_id"],
            content_type=record["content_type"],
            attribution=record["attribution"],
            confidence=record["confidence"],
            ai_likelihood=record["ai_likelihood"],
            signals=record["signals"],
            status=record["status"],
            content_hash_value=record["_content_hash"],
            preview=record["_preview"],
            details={
                "signal_disagreement": record["signal_disagreement"],
                "label_variant": record["transparency_label"]["variant"],
                "char_count": record["_char_count"],
                "word_count": record["_word_count"],
            },
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _public_record(record: dict) -> dict:
    """Strip internal (underscore-prefixed) fields before returning to clients."""
    return {k: v for k, v in record.items() if not k.startswith("_")}


def classify_text(
    conn: sqlite3.Connection, *, creator_id: str, text: str, detector
) -> dict:
    """Run the text pipeline and persist the result.

    ``detector`` is any object with an ``analyze(text) -> dict`` method (the Groq
    signal in production, a fake in tests).
    """
    llm = detector.analyze(text)
    stylo = stylometric_signal.analyze(text)
    phrase = phrase_signal.analyze(text)

    signals = {"llm_semantic": llm, "stylometric": stylo, "phrase_pattern": phrase}
    word_count = _word_count(text)
    result = scoring.score_text(signals, word_count)

    # Fewer than two signals available -> not enough for meaningful analysis.
    if result["insufficient_signals"]:
        raise service_unavailable(
            "Not enough detection signals are currently available to analyze "
            "this submission. Please try again later.",
            {"available_signals": sum(1 for s in signals.values() if s.get("available"))},
        )

    label = build_label(result["attribution"], short_sample=result["short_sample"])
    record = {
        "content_id": str(uuid.uuid4()),
        "creator_id": creator_id,
        "content_type": CONTENT_TYPE_TEXT,
        "attribution": result["attribution"],
        "ai_likelihood": result["ai_likelihood"],
        "confidence": result["confidence"],
        "status": STATUS_CLASSIFIED,
        "transparency_label": label,
        "signals": signals,
        "signal_disagreement": result["signal_disagreement"],
        "created_at": utcnow_iso(),
        "certificate": None,
        "_content_hash": audit.content_hash(text),
        "_char_count": len(text),
        "_word_count": word_count,
        "_preview": audit.make_preview(text),
    }
    _persist(
        conn,
        record=record,
        full_text=text,
        metadata=None,
        event_type=audit.EVENT_CLASSIFICATION,
    )
    return _public_record(record)


def classify_image_metadata(
    conn: sqlite3.Connection, *, creator_id: str, metadata: dict
) -> dict:
    """Run the image-metadata pipeline and persist the result."""
    from .detection import image_metadata_signal

    signals = image_metadata_signal.analyze(metadata)
    result = scoring.score_image(signals)

    if result["insufficient_signals"]:
        raise service_unavailable(
            "Not enough metadata signals are available to analyze this image."
        )

    label = build_label(result["attribution"], short_sample=False)
    canonical = json.dumps(metadata, sort_keys=True)
    preview_source = str(metadata.get("filename", "")) or "image metadata"
    record = {
        "content_id": str(uuid.uuid4()),
        "creator_id": creator_id,
        "content_type": CONTENT_TYPE_IMAGE,
        "attribution": result["attribution"],
        "ai_likelihood": result["ai_likelihood"],
        "confidence": result["confidence"],
        "status": STATUS_CLASSIFIED,
        "transparency_label": label,
        "signals": signals,
        "signal_disagreement": result["signal_disagreement"],
        "created_at": utcnow_iso(),
        "certificate": None,
        "_content_hash": audit.content_hash(canonical),
        "_char_count": len(canonical),
        "_word_count": 0,
        "_preview": audit.make_preview(preview_source),
    }
    _persist(
        conn,
        record=record,
        full_text=None,
        metadata=metadata,
        event_type=audit.EVENT_IMAGE_CLASSIFICATION,
    )
    return _public_record(record)
