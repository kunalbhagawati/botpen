"""Cross-agent read permissions over the mailbox (SQLModel).

ask / grant / deny / revoke / list / check, plus the change-feed the monitor relays. One row
per (asker, granter) pair. Each public function is wrapped by `core.db.transactional` (session
injected as `s`, committed on success).
"""

from __future__ import annotations

import fnmatch
import json

from sqlmodel import select

from ..core.db import transactional
from ..core.models import Permission, Session
from .utils import normalize_session, utc_now


def _ensure_sessions(s, *session_ids: str) -> None:
    now = utc_now()
    added = False
    for sid in session_ids:
        if s.get(Session, sid) is None:
            s.add(Session(session_id=sid, registered_at=now))
            added = True
    if added:
        s.flush()  # insert parent rows before any FK-referencing child in this transaction


def _get(s, asker: str, granter: str) -> Permission | None:
    return s.exec(
        select(Permission).where(Permission.asker == asker, Permission.granter == granter)
    ).first()


def _to_dict(p: Permission) -> dict:
    return {
        "id": p.id,
        "asker": p.asker,
        "granter": p.granter,
        "status": p.status,
        "ask_why": p.ask_why,
        "grant_why": p.grant_why,
        "paths": json.loads(p.paths) if p.paths else None,
        "revoked_at": p.revoked_at,
        "revoked_reason": p.revoked_reason,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@transactional
def ask_permission(s, asker: str, granter: str, ask_why: str | None = None) -> None:
    """`asker` requests read access to `granter`'s folder. Keeps an existing grant intact."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    now = utc_now()
    _ensure_sessions(s, asker, granter)
    p = _get(s, asker, granter)
    if p is None:
        p = Permission(asker=asker, granter=granter, status="requested", ask_why=ask_why, created_at=now, updated_at=now)
    else:
        p.ask_why = ask_why
        p.status = "granted" if p.status == "granted" else "requested"
        p.updated_at = now
    s.add(p)


@transactional
def grant_permission(s, granter: str, asker: str, paths: list, grant_why: str | None = None) -> None:
    """`granter` grants `asker` read access to `paths` (strings/globs). Clears any prior revoke.

    Raises ValueError if any path would expose `journal.jsonl` - a journal is always private.
    """
    bad = [p for p in paths if "journal.jsonl" in p or fnmatch.fnmatch("journal.jsonl", p)]
    if bad:
        raise ValueError(f"journal.jsonl is private and can never be granted (offending paths: {bad})")
    asker, granter = normalize_session(asker), normalize_session(granter)
    now = utc_now()
    _ensure_sessions(s, asker, granter)
    p = _get(s, asker, granter)
    if p is None:
        p = Permission(
            asker=asker, granter=granter, status="granted", grant_why=grant_why,
            paths=json.dumps(paths), created_at=now, updated_at=now,
        )
    else:
        p.status = "granted"
        p.grant_why = grant_why
        p.paths = json.dumps(paths)
        p.revoked_at = None
        p.revoked_reason = None
        p.updated_at = now
    s.add(p)


@transactional
def deny_permission(s, granter: str, asker: str, reason: str | None = None) -> int:
    """`granter` denies `asker`'s request (reason stored in grant_why). Returns rows affected."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    p = _get(s, asker, granter)
    if p is None:
        return 0
    p.status = "denied"
    p.grant_why = reason
    p.updated_at = utc_now()
    s.add(p)
    return 1


@transactional
def revoke_permission(s, granter: str, asker: str, reason: str | None = None) -> int:
    """`granter` revokes `asker`'s access. Returns the number of rows affected."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    now = utc_now()
    p = _get(s, asker, granter)
    if p is None:
        return 0
    p.status = "revoked"
    p.revoked_at = now
    p.revoked_reason = reason
    p.updated_at = now
    s.add(p)
    return 1


@transactional
def list_permissions(s, session_id: str) -> list[dict]:
    """All permission rows where `session_id` is the asker or the granter."""
    session_id = normalize_session(session_id)
    rows = s.exec(
        select(Permission)
        .where((Permission.asker == session_id) | (Permission.granter == session_id))
        # pyrefly: ignore [bad-argument-type]
        .order_by(Permission.id)
    ).all()
    return [_to_dict(p) for p in rows]


@transactional
def permissions_changed(s, session_id: str, after_ts: str) -> list[dict]:
    """Permission rows involving `session_id` updated after `after_ts` (ISO timestamp cursor).
    Used by the monitor to relay requests and decisions to both sides."""
    session_id = normalize_session(session_id)
    rows = s.exec(
        select(Permission)
        .where(
            (Permission.asker == session_id) | (Permission.granter == session_id),
            Permission.updated_at > after_ts,
        )
        # pyrefly: ignore [bad-argument-type]
        .order_by(Permission.updated_at, Permission.id)
    ).all()
    return [_to_dict(p) for p in rows]


@transactional
def can_read(s, asker: str, granter: str, path: str | None = None) -> dict:
    """Does `asker` hold a live grant on `granter`'s folder? Optionally test a specific `path`
    against the granted globs. Returns {allowed, paths}."""
    asker, granter = normalize_session(asker), normalize_session(granter)
    p = s.exec(
        select(Permission).where(
            Permission.asker == asker,
            Permission.granter == granter,
            Permission.status == "granted",
        )
    ).first()
    if p is None:
        return {"allowed": False, "paths": None}
    paths = json.loads(p.paths) if p.paths else []
    if path is None:
        return {"allowed": True, "paths": paths}
    allowed = any(g == path or fnmatch.fnmatch(path, g) for g in paths)
    return {"allowed": allowed, "paths": paths}
