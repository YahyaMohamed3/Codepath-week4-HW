"""HTTP routes for Provenance Guard.

Route handlers stay small: they validate input, delegate to service/domain
modules, and shape JSON responses. Structured errors are raised as ``APIError``
and translated centrally in the application factory.
"""

from __future__ import annotations

import json
import sqlite3

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    render_template,
    request,
)

from . import appeals, services
from .config import (
    CONTENT_TYPE_IMAGE,
    RATE_LIMIT_APPEAL,
    RATE_LIMIT_CERTIFICATE,
    RATE_LIMIT_IMAGE,
    RATE_LIMIT_SUBMIT,
    TEXT_MAX_CHARS,
    TEXT_MIN_CHARS,
)
from .errors import not_found, validation_error
from .extensions import limiter

bp = Blueprint("provenance", __name__)


# ---------------------------------------------------------------------------
# Connection helpers (one connection per request, closed on teardown).
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    if "db" not in g:
        from .database import get_connection

        g.db = get_connection(current_app.config["DATABASE_PATH"])
    return g.db


def _detector():
    return current_app.extensions["provenance_detector"]


def _require_json() -> dict:
    if not request.is_json:
        raise validation_error("Request body must be JSON.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise validation_error("Request body must be a JSON object.")
    return data


def _require_creator_id(data: dict) -> str:
    creator_id = data.get("creator_id")
    if not isinstance(creator_id, str) or not creator_id.strip():
        raise validation_error(
            "creator_id must be a non-empty string.", {"field": "creator_id"}
        )
    return creator_id.strip()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@bp.get("/health")
def health():
    db_ok = True
    try:
        get_db().execute("SELECT 1")
    except sqlite3.Error:
        db_ok = False
    return jsonify(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "groq_configured": current_app.config["GROQ_CONFIGURED"],
        }
    )


# ---------------------------------------------------------------------------
# Text submission
# ---------------------------------------------------------------------------
@bp.post("/submit")
@limiter.limit(RATE_LIMIT_SUBMIT)
def submit():
    data = _require_json()
    creator_id = _require_creator_id(data)

    text = data.get("text")
    if not isinstance(text, str):
        raise validation_error("text must be a string.", {"field": "text"})
    stripped = text.strip()
    if len(stripped) < TEXT_MIN_CHARS:
        raise validation_error(
            f"The text field must contain at least {TEXT_MIN_CHARS} characters.",
            {"field": "text"},
        )
    if len(text) > TEXT_MAX_CHARS:
        raise validation_error(
            f"The text field must not exceed {TEXT_MAX_CHARS} characters.",
            {"field": "text"},
        )

    result = services.classify_text(
        get_db(), creator_id=creator_id, text=text, detector=_detector()
    )
    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Image-metadata submission
# ---------------------------------------------------------------------------
@bp.post("/submit/image-metadata")
@limiter.limit(RATE_LIMIT_IMAGE)
def submit_image_metadata():
    data = _require_json()
    creator_id = _require_creator_id(data)

    metadata = data.get("metadata")
    if not isinstance(metadata, dict) or not metadata:
        raise validation_error(
            "metadata must be a non-empty JSON object.", {"field": "metadata"}
        )

    result = services.classify_image_metadata(
        get_db(), creator_id=creator_id, metadata=metadata
    )
    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Appeals
# ---------------------------------------------------------------------------
@bp.post("/appeal")
@limiter.limit(RATE_LIMIT_APPEAL)
def appeal():
    data = _require_json()
    creator_id = _require_creator_id(data)

    content_id = data.get("content_id")
    if not isinstance(content_id, str) or not content_id.strip():
        raise validation_error(
            "content_id must be a non-empty string.", {"field": "content_id"}
        )

    result = appeals.submit_appeal(
        get_db(),
        content_id=content_id.strip(),
        creator_id=creator_id,
        creator_reasoning=data.get("creator_reasoning", ""),
    )
    status = 200 if result.get("duplicate") else 201
    return jsonify(result), status


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@bp.get("/log")
def log():
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 500))

    rows = (
        get_db()
        .execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        .fetchall()
    )
    from .audit import row_to_event

    return jsonify({"count": len(rows), "events": [row_to_event(r) for r in rows]})


# ---------------------------------------------------------------------------
# Content lookup
# ---------------------------------------------------------------------------
@bp.get("/content/<content_id>")
def content(content_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM submissions WHERE content_id = ?", (content_id,)
    ).fetchone()
    if row is None:
        raise not_found(
            "No submission was found for that content_id.",
            {"content_id": content_id},
        )

    appeal_row = conn.execute(
        "SELECT * FROM appeals WHERE content_id = ?", (content_id,)
    ).fetchone()
    appeal_info = None
    if appeal_row is not None:
        appeal_info = {
            "appeal_id": appeal_row["appeal_id"],
            "status": appeal_row["status"],
            "creator_reasoning": appeal_row["creator_reasoning"],
            "submitted_at": appeal_row["submitted_at"],
            "original_attribution": appeal_row["original_attribution"],
            "original_confidence": appeal_row["original_confidence"],
        }

    from . import certificates

    certificate = certificates.certificate_for_content(conn, content_id)

    return jsonify(
        {
            "content_id": row["content_id"],
            "creator_id": row["creator_id"],
            "content_type": row["content_type"],
            "attribution": row["attribution"],
            "ai_likelihood": row["ai_likelihood"],
            "confidence": row["confidence"],
            "signal_disagreement": row["signal_disagreement"],
            "status": row["status"],
            "transparency_label": {
                "variant": row["label_variant"],
                "text": row["label_text"],
            },
            "signals": json.loads(row["signals_json"]),
            "created_at": row["created_at"],
            "appeal": appeal_info,
            "certificate": certificate,
        }
    )


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
@bp.post("/certificate/challenge")
@limiter.limit(RATE_LIMIT_CERTIFICATE)
def certificate_challenge():
    from . import certificates

    data = _require_json()
    creator_id = _require_creator_id(data)
    content_id = data.get("content_id")
    if not isinstance(content_id, str) or not content_id.strip():
        raise validation_error(
            "content_id must be a non-empty string.", {"field": "content_id"}
        )
    result = certificates.create_challenge(
        get_db(), content_id=content_id.strip(), creator_id=creator_id
    )
    return jsonify(result), 201


@bp.post("/certificate/verify")
@limiter.limit(RATE_LIMIT_CERTIFICATE)
def certificate_verify():
    from . import certificates

    data = _require_json()
    creator_id = _require_creator_id(data)
    for field in ("challenge_id", "content_id"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise validation_error(
                f"{field} must be a non-empty string.", {"field": field}
            )

    result = certificates.verify_challenge(
        get_db(),
        challenge_id=data["challenge_id"].strip(),
        content_id=data["content_id"].strip(),
        creator_id=creator_id,
        challenge_response=data.get("challenge_response", ""),
        creator_attestation=data.get("creator_attestation", False),
        draft_evidence=data.get("draft_evidence", []),
    )
    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Analytics (JSON) and dashboard (HTML)
# ---------------------------------------------------------------------------
@bp.get("/analytics")
def analytics_json():
    from . import analytics

    return jsonify(analytics.compute_analytics(get_db()))


@bp.get("/dashboard")
def dashboard():
    from . import analytics

    conn = get_db()
    stats = analytics.compute_analytics(conn)
    from .audit import row_to_event

    rows = (
        conn.execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC, rowid DESC LIMIT 8"
        ).fetchall()
    )
    recent = [row_to_event(r) for r in rows]
    return render_template("dashboard.html", stats=stats, recent=recent)


# ---------------------------------------------------------------------------
# Browser demo home
# ---------------------------------------------------------------------------
@bp.get("/")
def index():
    return render_template("index.html")
