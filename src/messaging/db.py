"""SQLite storage for the agent mailbox.

SQLite serializes writes itself (WAL + busy_timeout), so callers never manage a
lock and no agent can ever lock on behalf of another. A session id is just data;
each agent passes its own.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import arrow

from . import queries


def utc_now() -> str:
    return arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")


def normalize_session(session_id: str) -> str:
    """Canonicalize a UUID session id to 32-char lowercase hex (so dash/case differences
    never cause a mismatch). Non-UUID ids (e.g. test names) pass through unchanged."""
    try:
        return uuid.UUID(str(session_id)).hex
    except (ValueError, AttributeError, TypeError):
        return session_id


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
    path: str | None = None,
) -> None:
    """Insert or update a session's metadata. Supplied fields overwrite; omitted fields keep prior values."""
    session_id = normalize_session(session_id)
    conn.execute(
        queries.REGISTER_SESSION.substitute(),
        (session_id, utc_now(), model, description, thoughts, path),
    )
    conn.commit()


def write_message(
    conn: sqlite3.Connection,
    session_id: str,
    body: Any,
    extra: Any = None,
    to: list[str] | None = None,
) -> tuple[int, str]:
    """Append one message (body + optional extra). Auto-registers an unseen sender.

    `body` may be any JSON value (a string, object, array, number, ...). It and
    `extra` are stored JSON-encoded and round-tripped back to their original types
    on read. `to` is a list of recipient session ids (None/empty = everyone).
    """
    session_id = normalize_session(session_id)
    to = [normalize_session(t) for t in to] if to else None
    conn.execute(
        queries.ENSURE_SESSION.substitute(),
        (session_id, utc_now()),
    )
    ts = utc_now()
    cur = conn.execute(
        queries.INSERT_MESSAGE.substitute(),
        (
            session_id,
            ts,
            json.dumps(body),
            json.dumps(extra) if extra is not None else None,
            json.dumps(to) if to else None,
        ),
    )
    conn.commit()
    message_id = cur.lastrowid
    assert message_id is not None  # AUTOINCREMENT always yields a rowid after INSERT
    return message_id, ts


def write_thought(
    conn: sqlite3.Connection,
    session_id: str,
    thoughts: str,
    extra: Any = None,
) -> tuple[int, str]:
    """Append a thought to the thoughts log. Auto-registers an unseen session. `extra` (any
    JSON value) is stored JSON-encoded; `thoughts` is plain text."""
    session_id = normalize_session(session_id)
    conn.execute(queries.ENSURE_SESSION.substitute(), (session_id, utc_now()))
    ts = utc_now()
    cur = conn.execute(
        queries.INSERT_THOUGHT.substitute(),
        (session_id, ts, thoughts, json.dumps(extra) if extra is not None else None),
    )
    conn.commit()
    thought_id = cur.lastrowid
    assert thought_id is not None
    return thought_id, ts


def _row_to_message(row: sqlite3.Row) -> dict:
    extra = row["extra"]
    to = row["to"]
    return {
        "id": row["id"],
        "session": row["session_id"],
        "ts": row["ts"],
        "body": json.loads(row["msg"]),
        "extra": json.loads(extra) if extra is not None else None,
        "to": json.loads(to) if to is not None else None,
    }


def visible_to(message: dict, session_id: str) -> bool:
    """A message is visible to `session_id` if it is a broadcast (to is None), the session is
    a named recipient, or the session is the sender."""
    return message["to"] is None or session_id in message["to"] or message["session"] == session_id


def read_since_last(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Messages newer than this session's own last message, that are addressed to it
    (broadcast or a named recipient). If the session has never written, the whole history."""
    session_id = normalize_session(session_id)
    row = conn.execute(queries.LAST_MESSAGE_ID.substitute(), (session_id,)).fetchone()
    last = row["last"]
    if last is None:
        rows = conn.execute(queries.READ_ALL.substitute()).fetchall()
    else:
        rows = conn.execute(queries.READ_SINCE.substitute(), (last,)).fetchall()
    return [m for m in (_row_to_message(r) for r in rows) if visible_to(m, session_id)]


def read_after(conn: sqlite3.Connection, after_id: int, exclude_session: str | None = None) -> list[dict]:
    """All messages with id greater than `after_id` (any author), optionally excluding one
    session. Cursor-driven — for a monitor relaying everything new, independent of who wrote last."""
    rows = conn.execute(queries.READ_AFTER.substitute(), (after_id,)).fetchall()
    messages = [_row_to_message(r) for r in rows]
    if exclude_session is not None:
        exclude_session = normalize_session(exclude_session)
        messages = [m for m in messages if m["session"] != exclude_session]
    return messages


# --- cross-agent read permissions ---------------------------------------------------------

def _row_to_permission(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "asker": row["asker"],
        "granter": row["granter"],
        "status": row["status"],
        "ask_why": row["ask_why"],
        "grant_why": row["grant_why"],
        "paths": json.loads(row["paths"]) if row["paths"] else None,
        "revoked_at": row["revoked_at"],
        "revoked_reason": row["revoked_reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _ensure_sessions(conn: sqlite3.Connection, *session_ids: str) -> None:
    now = utc_now()
    for sid in session_ids:
        conn.execute(queries.ENSURE_SESSION.substitute(), (sid, now))


def ask_permission(conn: sqlite3.Connection, asker: str, granter: str, ask_why: str | None = None) -> None:
    """`asker` requests read access to `granter`'s folder. Keeps an existing grant intact."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    _ensure_sessions(conn, asker, granter)
    now = utc_now()
    conn.execute(queries.ASK_PERMISSION.substitute(), (asker, granter, ask_why, now, now))
    conn.commit()


def grant_permission(
    conn: sqlite3.Connection, granter: str, asker: str, paths: list, grant_why: str | None = None
) -> None:
    """`granter` grants `asker` read access to `paths` (strings/globs). Clears any prior revoke.

    Raises ValueError if any path would expose `journal.jsonl` — a journal is always private.
    """
    asker, granter = normalize_session(asker), normalize_session(granter)
    bad = [p for p in paths if "journal.jsonl" in p or fnmatch.fnmatch("journal.jsonl", p)]
    if bad:
        raise ValueError(f"journal.jsonl is private and can never be granted (offending paths: {bad})")
    _ensure_sessions(conn, asker, granter)
    now = utc_now()
    conn.execute(queries.GRANT_PERMISSION.substitute(), (asker, granter, grant_why, json.dumps(paths), now, now))
    conn.commit()


def deny_permission(conn: sqlite3.Connection, granter: str, asker: str, reason: str | None = None) -> int:
    """`granter` denies `asker`'s request (reason stored in grant_why). Returns rows affected."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    cur = conn.execute(queries.DENY_PERMISSION.substitute(), (reason, utc_now(), granter, asker))
    conn.commit()
    return cur.rowcount


def revoke_permission(conn: sqlite3.Connection, granter: str, asker: str, reason: str | None = None) -> int:
    """`granter` revokes `asker`'s access. Returns the number of rows affected."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    now = utc_now()
    cur = conn.execute(queries.REVOKE_PERMISSION.substitute(), (now, reason, now, granter, asker))
    conn.commit()
    return cur.rowcount


def list_permissions(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """All permission rows where `session_id` is the asker or the granter."""
    session_id = normalize_session(session_id)
    rows = conn.execute(queries.LIST_PERMISSIONS.substitute(), (session_id, session_id)).fetchall()
    return [_row_to_permission(r) for r in rows]


def permissions_changed(conn: sqlite3.Connection, session_id: str, after_ts: str) -> list[dict]:
    """Permission rows involving `session_id` (asker or granter) updated after `after_ts`
    (an ISO timestamp cursor). Used by the monitor to relay requests and decisions to both sides."""
    session_id = normalize_session(session_id)
    rows = conn.execute(queries.PERMISSIONS_CHANGED.substitute(), (session_id, session_id, after_ts)).fetchall()
    return [_row_to_permission(r) for r in rows]


def can_read(conn: sqlite3.Connection, asker: str, granter: str, path: str | None = None) -> dict:
    """Does `asker` hold a live grant on `granter`'s folder? Optionally test a specific `path`
    against the granted globs. Returns {allowed, paths}."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    row = conn.execute(queries.CHECK_PERMISSION.substitute(), (asker, granter)).fetchone()
    if row is None:
        return {"allowed": False, "paths": None}
    paths = json.loads(row["paths"]) if row["paths"] else []
    if path is None:
        return {"allowed": True, "paths": paths}
    allowed = any(p == path or fnmatch.fnmatch(path, p) for p in paths)
    return {"allowed": allowed, "paths": paths}
