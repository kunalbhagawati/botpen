"""Message, thought, and read operations over the mailbox (SQLModel).

JSON-bearing columns (`msg`, `extra`, `to`) use SQLAlchemy's JSON type - store and read
plain Python objects directly; no manual json-encoding/decoding.

The canonical agent identity is `scaffold_id`. `session_id` is the incarnation that sent
the message (lineage metadata).
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from ..core.db import atomic, with_session
from ..core.models import Message, Session, Thought
from .utils import normalize_session, utc_now


@atomic
def write_message(
    s,
    scaffold_id: str,
    session_id: str,
    body: Any,
    extra: Any = None,
    to: list[str] | None = None,
) -> tuple[int, str]:
    """Append one message (body + optional extra + optional recipient list).

    `body`/`extra` may be any JSON-serializable value. `to` is a list of recipient scaffold
    ids (None = broadcast to everyone). Returns (id, created_at).
    """
    session_id = normalize_session(session_id)
    normalized_to = [normalize_session(t) for t in to] if to else None
    ts = utc_now()
    m = Message(
        scaffold_id=scaffold_id,
        session_id=session_id,
        created_at=ts,
        msg=body,
        extra=extra,
        to=normalized_to,
    )
    s.add(m)
    s.flush()
    assert m.id is not None
    return m.id, ts


@atomic
def write_thought(
    s,
    scaffold_id: str,
    session_id: str,
    thoughts: str,
    extra: Any = None,
) -> tuple[int, str]:
    """Append a thought to the thoughts log. Returns (id, created_at)."""
    session_id = normalize_session(session_id)
    ts = utc_now()
    t = Thought(
        scaffold_id=scaffold_id,
        session_id=session_id,
        created_at=ts,
        thoughts=thoughts,
        extra=extra,
    )
    s.add(t)
    s.flush()
    assert t.id is not None
    return t.id, ts


def _msg_to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "scaffold": m.scaffold_id,
        "session": m.session_id,
        "created_at": m.created_at,
        "body": m.msg,
        "extra": m.extra,
        "to": m.to,
    }


def _thought_to_dict(t: Thought) -> dict:
    return {
        "id": t.id,
        "scaffold": t.scaffold_id,
        "session": t.session_id,
        "created_at": t.created_at,
        "thoughts": t.thoughts,
        "extra": t.extra,
    }


def visible_to(message: dict, scaffold_id: str) -> bool:
    """A message is visible to `scaffold_id` if it is a broadcast (to is None), the scaffold
    is a named recipient, or the scaffold is the sender."""
    return message["to"] is None or scaffold_id in message["to"] or message["scaffold"] == scaffold_id


@with_session
def read_since_last(s, scaffold_id: str) -> list[dict]:
    """Messages newer than this scaffold's own last message, addressed to it (broadcast or
    named recipient). If the scaffold has never written, returns the whole visible history."""
    last = s.exec(
        # pyrefly: ignore [missing-attribute]
        select(Message.id).where(Message.scaffold_id == scaffold_id).order_by(Message.id.desc())
    ).first()
    # pyrefly: ignore [bad-argument-type]
    stmt = select(Message).order_by(Message.id)
    if last is not None:
        stmt = stmt.where(Message.id > last)
    msgs = [_msg_to_dict(m) for m in s.exec(stmt).all()]
    return [m for m in msgs if visible_to(m, scaffold_id)]


@with_session
def read_after(s, after_id: int, exclude_scaffold: str | None = None) -> list[dict]:
    """All messages with id > `after_id`, optionally excluding one scaffold's messages.
    Cursor-driven - for a monitor relaying everything new."""
    # pyrefly: ignore [bad-argument-type, unsupported-operation]
    rows = s.exec(select(Message).where(Message.id > after_id).order_by(Message.id)).all()
    msgs = [_msg_to_dict(m) for m in rows]
    if exclude_scaffold is not None:
        msgs = [m for m in msgs if m["scaffold"] != exclude_scaffold]
    return msgs


@with_session
def read_thoughts(s, owner_session_id: str, caller_session_id: str) -> list[dict]:
    """Thoughts for `owner_session_id`, readable by `caller_session_id`.

    If owner != caller, checks that caller is in owner's `thoughts_readers` list. Returns []
    if not permitted. Both session_ids are normalized before comparison.
    """
    owner_session_id = normalize_session(owner_session_id)
    caller_session_id = normalize_session(caller_session_id)
    if owner_session_id != caller_session_id:
        owner_row = s.get(Session, owner_session_id)
        if owner_row is None:
            return []
        readers = owner_row.thoughts_readers or []
        if caller_session_id not in readers:
            return []
    # pyrefly: ignore [bad-argument-type]
    rows = s.exec(select(Thought).where(Thought.session_id == owner_session_id).order_by(Thought.id)).all()
    return [_thought_to_dict(t) for t in rows]
