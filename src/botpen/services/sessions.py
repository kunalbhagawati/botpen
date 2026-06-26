"""Session (incarnation) operations: register, resolve the active session, profile, chosen-stack,
and the thoughts-read grant list.

A `Session` is one incarnation running inside a scaffold (the durable agent). The daemon resolves
the scaffold from the token, then the *active* session (the latest registered, not-yet-stopped
incarnation) to stamp on the rows that incarnation produces. JSON columns (`chosen_stack`,
`thoughts_readers`) are plain Python objects.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from ..core.db import atomic, with_session
from ..core.models import Session
from .utils import normalize_session, utc_now


def _active(s, scaffold_id: str) -> Session | None:
    """The latest registered, not-yet-stopped incarnation for a scaffold (uses the caller's `s`)."""
    return s.exec(
        select(Session)
        .where(Session.scaffold_id == scaffold_id, Session.stopped_at.is_(None))
        .order_by(Session.registered_at.desc())
    ).first()


@atomic
def register(
    s,
    session_id: str,
    scaffold_id: str,
    model: str | None = None,
    description: str | None = None,
    agent_personality: str | None = None,
) -> None:
    """Insert or update an incarnation's metadata, linked to its scaffold.

    Anti-spoof: a session_id already owned by a different scaffold cannot be (re)registered - an
    agent can see peers' session_ids in `read` results, so without this it could hijack one by
    re-registering it under its own scaffold."""
    session_id = normalize_session(session_id)
    row = s.get(Session, session_id)
    if row is None:
        row = Session(session_id=session_id, registered_at=utc_now())
    elif row.scaffold_id != scaffold_id:
        raise PermissionError(f"session {session_id} belongs to another scaffold")
    row.scaffold_id = scaffold_id
    if model is not None:
        row.model = model
    if description is not None:
        row.description = description
    if agent_personality is not None:
        row.agent_personality = agent_personality
    s.add(row)


@with_session
def active_session_id(s, scaffold_id: str) -> str | None:
    """The scaffold's active incarnation id, or None if it has not registered yet."""
    row = _active(s, scaffold_id)
    return row.session_id if row else None


@with_session
def get_profile(s, scaffold_id: str) -> dict | None:
    """Public profile of the scaffold's active incarnation."""
    row = _active(s, scaffold_id)
    if row is None:
        return None
    return {
        "session_id": row.session_id,
        "model": row.model,
        "description": row.description,
        "personality": row.agent_personality,
    }


@with_session
def get_chosen_stack(s, scaffold_id: str) -> Any:
    """The active incarnation's chosen-stack JSON (already a Python object), or None."""
    row = _active(s, scaffold_id)
    return row.chosen_stack if row else None


@atomic
def set_chosen_stack(s, scaffold_id: str, stack: Any) -> None:
    """Store the active incarnation's chosen-stack (free-form, unvalidated)."""
    row = _active(s, scaffold_id)
    if row is None:
        return
    row.chosen_stack = stack
    s.add(row)


@with_session
def get_thoughts_readers(s, scaffold_id: str) -> list[str]:
    """The session_ids the active incarnation has granted thoughts-read access to."""
    row = _active(s, scaffold_id)
    return list(row.thoughts_readers or []) if row else []


@atomic
def grant_thoughts(s, scaffold_id: str, peer_session_id: str) -> None:
    """Let `peer_session_id` read the active incarnation's thoughts."""
    row = _active(s, scaffold_id)
    if row is None:
        return
    peer = normalize_session(peer_session_id)
    readers = list(row.thoughts_readers or [])
    if peer not in readers:
        readers.append(peer)
        row.thoughts_readers = readers  # reassign so the JSON column registers the change
        s.add(row)


@atomic
def revoke_thoughts(s, scaffold_id: str, peer_session_id: str) -> None:
    """Stop `peer_session_id` from reading the active incarnation's thoughts."""
    row = _active(s, scaffold_id)
    if row is None:
        return
    peer = normalize_session(peer_session_id)
    row.thoughts_readers = [r for r in (row.thoughts_readers or []) if r != peer]
    s.add(row)
