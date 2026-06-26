"""Daemon request log: one row per RPC the daemon serves.

Thrift's binary RPC is not curl-debuggable, so this is the observability story - the operator
can inspect exactly what each agent called. Token redaction is off by default (local,
single-operator system); flip `REQUEST_LOG_REDACT_TOKEN` to scrub token/secret_key from stored
payloads.

`request` is a JSON column - store/read plain Python objects directly; no manual json-encoding.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from config import settings

from ..core.db import atomic, with_session
from ..core.models import RequestLog
from .utils import utc_now

_REDACTED = "***"
_SECRET_KEYS = {"token", "secret_key"}


def _redact(value: Any) -> Any:
    """Recursively replace any token/secret_key field so it never lands in the log."""
    if isinstance(value, dict):
        return {k: (_REDACTED if k in _SECRET_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _to_dict(r: RequestLog) -> dict:
    return {
        "id": r.id,
        "created_at": r.created_at,
        "method": r.method,
        "scaffold_id": r.scaffold_id,
        "request": r.request,
        "status": r.status,
        "error": r.error,
        "duration_ms": r.duration_ms,
    }


@atomic
def record(
    s,
    method: str,
    scaffold_id: str | None = None,
    request: Any = None,
    status: str = "ok",
    error: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Append one request-log row. Redacts token/secret_key only if REQUEST_LOG_REDACT_TOKEN."""
    payload = _redact(request) if (request is not None and settings.REQUEST_LOG_REDACT_TOKEN) else request
    s.add(
        RequestLog(
            created_at=utc_now(),
            method=method,
            scaffold_id=scaffold_id,
            request=payload,
            status=status,
            error=error,
            duration_ms=duration_ms,
        )
    )


@with_session
def list_requests(s, scaffold_id: str | None = None, limit: int = 100) -> list[dict]:
    """Most-recent requests first, optionally filtered to one scaffold."""
    stmt = select(RequestLog)
    if scaffold_id is not None:
        stmt = stmt.where(RequestLog.scaffold_id == scaffold_id)
    rows = s.exec(stmt.order_by(RequestLog.id.desc()).limit(limit)).all()
    return [_to_dict(r) for r in rows]
