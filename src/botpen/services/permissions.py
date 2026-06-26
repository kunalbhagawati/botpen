"""Host-mediated shared-volume permissions over the mailbox (SQLModel).

Folder-read grants are no longer advisory: an agent asks the host to apply POSIX ACLs on
paths inside its own `/shared/<slug>/`, and every action is recorded here as an append-only
log row (requested -> applied / revoked / failed). This module owns only the log; applying
the actual ACLs (via a helper container) lives in the docker layer and calls
`mark_applied`/`mark_failed`.

The canonical agent identity is `scaffold_id`. `grant` is a JSON column - store/read plain
Python objects directly; no manual json-encoding.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from ..core.db import atomic, with_session
from ..core.models import PermissionLog
from .utils import utc_now


def _to_dict(p: PermissionLog) -> dict:
    return {
        "id": p.id,
        "permission_type": p.permission_type,
        "owner": p.owner_scaffold_id,
        "peer": p.peer_scaffold_id,
        "grant": p.grant,
        "peer_permission_request_reason": p.peer_permission_request_reason,
        "owner_permission_decision_reason": p.owner_permission_decision_reason,
        "status": p.status,
        "error": p.error,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "applied_at": p.applied_at,
    }


@atomic
def log_ask(s, owner_scaffold: str, peer_scaffold: str, reason: str | None = None) -> dict:
    """Record `peer_scaffold` asking `owner_scaffold` for access. No ACL is applied - this is a
    relayable request the owner acts on with a grant."""
    now = utc_now()
    row = PermissionLog(
        permission_type="ask",
        owner_scaffold_id=owner_scaffold,
        peer_scaffold_id=peer_scaffold,
        peer_permission_request_reason=reason,
        status="requested",
        created_at=now,
        updated_at=now,
    )
    s.add(row)
    s.flush()
    return _to_dict(row)


@atomic
def log_grant(s, owner_scaffold: str, peer_scaffold: str, grant: Any, reason: str | None = None) -> dict:
    """Record `owner_scaffold` granting `peer_scaffold` access described by the `grant` tree
    (paths under the owner's `/shared/<slug>/`). Returns the row at status `requested`; the ACL
    layer flips it to `applied`/`failed`."""
    now = utc_now()
    row = PermissionLog(
        permission_type="grant",
        owner_scaffold_id=owner_scaffold,
        peer_scaffold_id=peer_scaffold,
        grant=grant,
        owner_permission_decision_reason=reason,
        status="requested",
        created_at=now,
        updated_at=now,
    )
    s.add(row)
    s.flush()
    return _to_dict(row)


@atomic
def log_revoke(
    s,
    owner_scaffold: str,
    peer_scaffold: str,
    grant: Any = None,
    reason: str | None = None,
) -> dict:
    """Record `owner_scaffold` revoking `peer_scaffold`'s access (optionally scoped to the
    `grant` tree). Returns the row at status `requested` (the ACL layer flips it to
    `revoked`/`failed`)."""
    now = utc_now()
    row = PermissionLog(
        permission_type="revoke",
        owner_scaffold_id=owner_scaffold,
        peer_scaffold_id=peer_scaffold,
        grant=grant,
        owner_permission_decision_reason=reason,
        status="requested",
        created_at=now,
        updated_at=now,
    )
    s.add(row)
    s.flush()
    return _to_dict(row)


@atomic
def mark_applied(s, log_id: int) -> None:
    """Mark a logged grant/revoke as carried out (ACL applied on the volume)."""
    row = s.get(PermissionLog, log_id)
    if row is None:
        return
    now = utc_now()
    row.status = "revoked" if row.permission_type == "revoke" else "applied"
    row.applied_at = now
    row.updated_at = now
    s.add(row)


@atomic
def mark_failed(s, log_id: int, error: str) -> None:
    """Mark a logged action as failed, recording the error."""
    row = s.get(PermissionLog, log_id)
    if row is None:
        return
    row.status = "failed"
    row.error = error
    row.updated_at = utc_now()
    s.add(row)


@with_session
def list_log(s, scaffold_id: str | None = None) -> list[dict]:
    """The permission log, optionally filtered to rows where `scaffold_id` is owner or peer."""
    stmt = select(PermissionLog)
    if scaffold_id is not None:
        stmt = stmt.where(
            (PermissionLog.owner_scaffold_id == scaffold_id) | (PermissionLog.peer_scaffold_id == scaffold_id)
        )
    rows = s.exec(stmt.order_by(PermissionLog.id)).all()
    return [_to_dict(p) for p in rows]
