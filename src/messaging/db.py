"""SQLite storage for the agent mailbox.

SQLite serializes writes itself (WAL + busy_timeout), so callers never manage a
lock and no agent can ever lock on behalf of another. A session id is just data;
each agent passes its own.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id    TEXT PRIMARY KEY,
            registered_at TEXT NOT NULL,
            other         TEXT,
            telemetry     TEXT,
            params        TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            ts         TEXT NOT NULL,
            msg        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """
    )
    conn.commit()


def reset(conn: sqlite3.Connection) -> None:
    """Drop all mailbox tables and recreate the empty schema. DESTRUCTIVE."""
    conn.executescript("DROP TABLE IF EXISTS messages; DROP TABLE IF EXISTS sessions;")
    conn.commit()
    _init(conn)


def register(
    conn: sqlite3.Connection,
    session_id: str,
    other: str | None = None,
    telemetry: str | None = None,
    params: str | None = None,
) -> None:
    """Insert or update a session's metadata. Supplied fields overwrite; omitted fields keep prior values."""
    conn.execute(
        """
        INSERT INTO sessions (session_id, registered_at, other, telemetry, params)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            other     = COALESCE(excluded.other,     sessions.other),
            telemetry = COALESCE(excluded.telemetry, sessions.telemetry),
            params    = COALESCE(excluded.params,    sessions.params)
        """,
        (session_id, utc_now(), other, telemetry, params),
    )
    conn.commit()


def write_message(conn: sqlite3.Connection, session_id: str, msg: str) -> tuple[int, str]:
    """Append a message. Auto-registers a bare session row if the sender is unseen."""
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, registered_at) VALUES (?, ?)",
        (session_id, utc_now()),
    )
    ts = utc_now()
    cur = conn.execute(
        "INSERT INTO messages (session_id, ts, msg) VALUES (?, ?, ?)",
        (session_id, ts, msg),
    )
    conn.commit()
    message_id = cur.lastrowid
    assert message_id is not None  # AUTOINCREMENT always yields a rowid after INSERT
    return message_id, ts


def read_since_last(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """All messages newer than this session's own last message.

    If the session has never written, return the entire history.
    """
    row = conn.execute(
        "SELECT MAX(id) AS last FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()
    last = row["last"]
    if last is None:
        rows = conn.execute(
            "SELECT id, session_id, ts, msg FROM messages ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, session_id, ts, msg FROM messages WHERE id > ? ORDER BY id",
            (last,),
        ).fetchall()
    return [dict(r) for r in rows]
