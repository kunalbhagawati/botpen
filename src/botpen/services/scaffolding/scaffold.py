"""The Scaffold provisioning record: mint identity + token, CRUD.

A Scaffold row is created at `scaffold new` time, before any claude session exists. The
`secret_key` is the per-agent token the daemon authenticates; `scaffold_id` is the canonical
durable identity used everywhere.

`stack` is a JSON column - store/read plain Python objects directly; no manual json-encoding.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from sqlmodel import select

from config import settings

from ...core.db import atomic, with_session
from ...core.models import Scaffold
from ..utils import utc_now


def _to_dict(sc: Scaffold) -> dict:
    return {
        "scaffold_id": sc.scaffold_id,
        "slug": sc.scaffold_slug,
        "created_at": sc.created_at,
        "secret_key": sc.secret_key,
        "uid": sc.uid,
        "gid": sc.gid,
        "max_disk_mb": sc.max_disk_mb,
        "stack": sc.stack,
        "image_tag": sc.image_tag,
        "container_name": sc.container_name,
        "status": sc.status,
    }


def _next_uid_gid(s) -> tuple[int, int]:
    """Allocate the next free uid/gid (max existing + 1, from the configured bases). Using
    max+1 rather than a count avoids collisions if a scaffold row is ever removed."""
    used = s.exec(select(Scaffold.uid)).all()
    uid = (max(used) + 1) if used else settings.SCAFFOLD_UID_BASE
    gid = settings.SCAFFOLD_GID_BASE + (uid - settings.SCAFFOLD_UID_BASE)
    return uid, gid


@atomic
def create_scaffold(s, slug: str, max_disk_mb: int, stack: Any = None) -> dict:
    """Mint a new scaffold (uuid + secret token + uid/gid) and persist it at status `created`."""
    uid, gid = _next_uid_gid(s)
    row = Scaffold(
        scaffold_id=uuid.uuid4().hex,
        scaffold_slug=slug,
        created_at=utc_now(),
        secret_key=secrets.token_urlsafe(32),
        uid=uid,
        gid=gid,
        max_disk_mb=max_disk_mb,
        stack=stack,
        status="created",
    )
    s.add(row)
    s.flush()
    return _to_dict(row)


@with_session
def get_by_secret_key(s, secret_key: str) -> dict | None:
    """Resolve a scaffold by its token (the daemon's auth lookup). None if unknown."""
    row = s.exec(select(Scaffold).where(Scaffold.secret_key == secret_key)).first()
    return _to_dict(row) if row else None


@with_session
def get_by_id(s, scaffold_id: str) -> dict | None:
    """Resolve a scaffold by its canonical id. None if unknown."""
    row = s.get(Scaffold, scaffold_id)
    return _to_dict(row) if row else None


@atomic
def set_status(
    s,
    scaffold_id: str,
    status: str,
    container_name: str | None = None,
    image_tag: str | None = None,
) -> None:
    """Update a scaffold's lifecycle status and (optionally) its container/image identifiers."""
    row = s.get(Scaffold, scaffold_id)
    if row is None:
        return
    row.status = status
    if container_name is not None:
        row.container_name = container_name
    if image_tag is not None:
        row.image_tag = image_tag
    s.add(row)


@with_session
def list_scaffolds(s) -> list[dict]:
    """All scaffolds, oldest first."""
    rows = s.exec(select(Scaffold).order_by(Scaffold.created_at)).all()
    return [_to_dict(sc) for sc in rows]
