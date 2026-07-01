"""SQLite persistence layer for Provenance Guard.

Uses Python's built-in ``sqlite3`` with parameterized queries only. Foreign keys
are enabled on every connection. Tables are created automatically at startup.
Timestamps are stored as UTC ISO-8601 strings with a ``Z`` suffix.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def get_connection(database_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row access by name and foreign keys on."""
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    content_id      TEXT PRIMARY KEY,
    creator_id      TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    attribution     TEXT NOT NULL,
    ai_likelihood   REAL NOT NULL,
    confidence      REAL NOT NULL,
    signal_disagreement REAL NOT NULL,
    status          TEXT NOT NULL,
    label_variant   TEXT NOT NULL,
    label_text      TEXT NOT NULL,
    signals_json    TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    char_count      INTEGER NOT NULL,
    word_count      INTEGER NOT NULL,
    preview         TEXT NOT NULL,
    full_text       TEXT,
    metadata_json   TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    content_id      TEXT,
    creator_id      TEXT,
    content_type    TEXT,
    attribution     TEXT,
    confidence      REAL,
    ai_likelihood   REAL,
    signals_json    TEXT,
    status          TEXT,
    content_hash    TEXT,
    preview         TEXT,
    details_json    TEXT NOT NULL,
    FOREIGN KEY (content_id) REFERENCES submissions(content_id)
);

CREATE TABLE IF NOT EXISTS appeals (
    appeal_id       TEXT PRIMARY KEY,
    content_id      TEXT NOT NULL,
    creator_id      TEXT NOT NULL,
    creator_reasoning TEXT NOT NULL,
    status          TEXT NOT NULL,
    original_attribution TEXT NOT NULL,
    original_confidence  REAL NOT NULL,
    original_ai_likelihood REAL NOT NULL,
    submitted_at    TEXT NOT NULL,
    FOREIGN KEY (content_id) REFERENCES submissions(content_id)
);

CREATE TABLE IF NOT EXISTS certificate_challenges (
    challenge_id    TEXT PRIMARY KEY,
    content_id      TEXT NOT NULL,
    creator_id      TEXT NOT NULL,
    phrase          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (content_id) REFERENCES submissions(content_id)
);

CREATE TABLE IF NOT EXISTS certificates (
    certificate_id  TEXT PRIMARY KEY,
    content_id      TEXT NOT NULL,
    creator_id      TEXT NOT NULL,
    challenge_id    TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    issued_at       TEXT NOT NULL,
    FOREIGN KEY (content_id) REFERENCES submissions(content_id),
    FOREIGN KEY (challenge_id) REFERENCES certificate_challenges(challenge_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_submissions_creator ON submissions(creator_id);
"""


def init_db(database_path: str) -> None:
    """Create all tables and indexes if they do not already exist."""
    conn = get_connection(database_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
