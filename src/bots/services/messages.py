"""Message, thought, and read operations over the mailbox (SQLModel).

Each public function is wrapped by `core.db.transactional`: it opens a session, passes it as
the first arg `s`, and commits on success. Callers pass everything *after* `s`. JSON-bearing
fields (`body`/`extra`/`to`) are json-encoded into TEXT columns and decoded on read.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import select

from ..core.db import transactional
from ..core.models import Message, Session, Thought
from .utils import normalize_session, utc_now


def _ensure_session(s, session_id: str) -> None:
    if s.get(Session, session_id) is None:
        s.add(Session(session_id=session_id, registered_at=utc_now()))
        s.flush()  # insert the parent row before any FK-referencing child in this transaction


@transactional
def register(
    s,
    session_id: str,
    model: str | None = None,
    description: str | None = None,
    thoughts: str | None = None,
    path: str | None = None,
) -> None:
    """Insert or update a session's metadata. Supplied fields overwrite; omitted fields keep prior values."""
    session_id = normalize_session(session_id)
    row = s.get(Session, session_id) or Session(session_id=session_id, registered_at=utc_now())
    if model is not None:
        row.model = model
    if description is not None:
        row.description = description
    if thoughts is not None:
        row.thoughts = thoughts
    if path is not None:
        row.path = path
    s.add(row)


@transactional
def write_message(s, session_id: str, body: Any, extra: Any = None, to: list[str] | None = None) -> tuple[int, str]:
    """Append one message (body + optional extra). Auto-registers an unseen sender.

    `body`/`extra` may be any JSON value (round-tripped on read). `to` is a list of recipient
    session ids (None/empty = everyone).
    """
    session_id = normalize_session(session_id)
    to_norm = [normalize_session(t) for t in to] if to else None
    ts = utc_now()
    _ensure_session(s, session_id)
    m = Message(
        session_id=session_id,
        ts=ts,
        msg=json.dumps(body),
        extra=json.dumps(extra) if extra is not None else None,
        to=json.dumps(to_norm) if to_norm else None,
    )
    s.add(m)
    s.flush()
    assert m.id is not None
    return m.id, ts


@transactional
def write_thought(s, session_id: str, thoughts: str, extra: Any = None) -> tuple[int, str]:
    """Append a thought to the thoughts log. Auto-registers an unseen session."""
    session_id = normalize_session(session_id)
    ts = utc_now()
    _ensure_session(s, session_id)
    t = Thought(
        session_id=session_id,
        ts=ts,
        thoughts=thoughts,
        extra=json.dumps(extra) if extra is not None else None,
    )
    s.add(t)
    s.flush()
    assert t.id is not None
    return t.id, ts


def _to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "session": m.session_id,
        "ts": m.ts,
        "body": json.loads(m.msg),
        "extra": json.loads(m.extra) if m.extra is not None else None,
        "to": json.loads(m.to) if m.to is not None else None,
    }


def visible_to(message: dict, session_id: str) -> bool:
    """A message is visible to `session_id` if it is a broadcast (to is None), the session is
    a named recipient, or the session is the sender."""
    return message["to"] is None or session_id in message["to"] or message["session"] == session_id


@transactional
def read_since_last(s, session_id: str) -> list[dict]:
    """Messages newer than this session's own last message, addressed to it (broadcast or a
    named recipient). If the session has never written, the whole visible history."""
    session_id = normalize_session(session_id)
    last = s.exec(
        # pyrefly: ignore [missing-attribute]
        select(Message.id).where(Message.session_id == session_id).order_by(Message.id.desc())
    ).first()
    # pyrefly: ignore [bad-argument-type]
    stmt = select(Message).order_by(Message.id)
    if last is not None:
        stmt = stmt.where(Message.id > last)
    msgs = [_to_dict(m) for m in s.exec(stmt).all()]
    return [m for m in msgs if visible_to(m, session_id)]


@transactional
def read_after(s, after_id: int, exclude_session: str | None = None) -> list[dict]:
    """All messages with id greater than `after_id` (any author), optionally excluding one
    session. Cursor-driven - for a monitor relaying everything new."""
    # pyrefly: ignore [bad-argument-type, unsupported-operation]
    rows = s.exec(select(Message).where(Message.id > after_id).order_by(Message.id)).all()
    msgs = [_to_dict(m) for m in rows]
    if exclude_session is not None:
        exclude_session = normalize_session(exclude_session)
        msgs = [m for m in msgs if m["session"] != exclude_session]
    return msgs
