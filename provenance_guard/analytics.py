"""Aggregate analytics over stored submissions and events.

All ratios guard against an empty database (no division by zero).
"""

from __future__ import annotations

import sqlite3

from .config import (
    ATTR_LIKELY_AI,
    ATTR_LIKELY_HUMAN,
    ATTR_UNCERTAIN,
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_TEXT,
    STATUS_UNDER_REVIEW,
)


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def compute_analytics(conn: sqlite3.Connection) -> dict:
    """Return the analytics summary as a JSON-serializable dict."""
    total = conn.execute("SELECT COUNT(*) AS n FROM submissions").fetchone()["n"]

    def count_where(clause: str, params: tuple = ()) -> int:
        return conn.execute(
            f"SELECT COUNT(*) AS n FROM submissions WHERE {clause}", params
        ).fetchone()["n"]

    text_count = count_where("content_type = ?", (CONTENT_TYPE_TEXT,))
    image_count = count_where("content_type = ?", (CONTENT_TYPE_IMAGE,))
    ai_count = count_where("attribution = ?", (ATTR_LIKELY_AI,))
    human_count = count_where("attribution = ?", (ATTR_LIKELY_HUMAN,))
    uncertain_count = count_where("attribution = ?", (ATTR_UNCERTAIN,))
    under_review = count_where("status = ?", (STATUS_UNDER_REVIEW,))

    # Appeals: count unique appealed submissions for a fair appeal rate.
    appeal_count = conn.execute("SELECT COUNT(*) AS n FROM appeals").fetchone()["n"]
    unique_appealed = conn.execute(
        "SELECT COUNT(DISTINCT content_id) AS n FROM appeals"
    ).fetchone()["n"]
    certificate_count = conn.execute(
        "SELECT COUNT(*) AS n FROM certificates"
    ).fetchone()["n"]

    avg_row = conn.execute(
        "SELECT AVG(confidence) AS c, AVG(signal_disagreement) AS d FROM submissions"
    ).fetchone()
    avg_confidence = round(avg_row["c"], 4) if avg_row["c"] is not None else 0.0
    avg_disagreement = round(avg_row["d"], 4) if avg_row["d"] is not None else 0.0

    return {
        "total_submissions": total,
        "text_submissions": text_count,
        "image_metadata_submissions": image_count,
        "likely_ai_count": ai_count,
        "likely_ai_ratio": _ratio(ai_count, total),
        "likely_human_count": human_count,
        "likely_human_ratio": _ratio(human_count, total),
        "uncertain_count": uncertain_count,
        "uncertain_ratio": _ratio(uncertain_count, total),
        "appeal_count": appeal_count,
        "appeal_rate": _ratio(unique_appealed, total),
        "average_confidence": avg_confidence,
        "average_signal_disagreement": avg_disagreement,
        "certificate_count": certificate_count,
        "under_review_count": under_review,
    }
