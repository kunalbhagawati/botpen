"""SQLite storage for the agent mailbox.

SQLite serializes writes itself (WAL + busy_timeout), so callers never manage a
lock and no agent can ever lock on behalf of another. A session id is just data;
each agent passes its own.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import arrow

from . import queries


def utc_now() -> str:
    return arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")


def migrate_sql_path() -> Path:
    """Locate migrate.sql (the schema). Honors MESSAGES_ROOT, else the project root."""
    root = os.environ.get("MESSAGES_ROOT")
    if root:
        candidate = Path(root) / "migrate.sql"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2] / "migrate.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(migrate_sql_path().read_text())
    conn.commit()


def reset(conn: sqlite3.Connection) -> None:
    """Drop all mailbox tables and recreate the empty schema. DESTRUCTIVE."""
    conn.executescript(queries.DROP_TABLES.substitute())
    conn.commit()
    _init(conn)


def register(
    conn: sqlite3.Connection,
    session_id: str,
    model: str | None = None,
    description: str | None = None,
    thoughts: str | None = None,
) -> None:
    """Insert or update a session's metadata. Supplied fields overwrite; omitted fields keep prior values."""
    conn.execute(
        queries.REGISTER_SESSION.substitute(),
        (session_id, utc_now(), model, description, thoughts),
    )
    conn.commit()


def write_message(
    conn: sqlite3.Connection,
    session_id: str,
    body: Any,
    extra: Any = None,
) -> tuple[int, str]:
    """Append one message (body + optional extra). Auto-registers an unseen sender.

    `body` may be any JSON value (a string, object, array, number, ...). It and
    `extra` are stored JSON-encoded and round-tripped back to their original types
    on read.
    """
    conn.execute(
        queries.ENSURE_SESSION.substitute(),
        (session_id, utc_now()),
    )
    ts = utc_now()
    cur = conn.execute(
        queries.INSERT_MESSAGE.substitute(),
        (session_id, ts, json.dumps(body), json.dumps(extra) if extra is not None else None),
    )
    conn.commit()
    message_id = cur.lastrowid
    assert message_id is not None  # AUTOINCREMENT always yields a rowid after INSERT
    return message_id, ts


def _row_to_message(row: sqlite3.Row) -> dict:
    extra = row["extra"]
    return {
        "id": row["id"],
        "session": row["session_id"],
        "ts": row["ts"],
        "body": json.loads(row["msg"]),
        "extra": json.loads(extra) if extra is not None else None,
    }


def read_since_last(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """All messages newer than this session's own last message.

    If the session has never written, return the entire history.
    """
    row = conn.execute(queries.LAST_MESSAGE_ID.substitute(), (session_id,)).fetchone()
    last = row["last"]
    if last is None:
        rows = conn.execute(queries.READ_ALL.substitute()).fetchall()
    else:
        rows = conn.execute(queries.READ_SINCE.substitute(), (last,)).fetchall()
    return [_row_to_message(r) for r in rows]
