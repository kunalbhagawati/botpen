"""Data-domain helpers shared across the service modules."""

from __future__ import annotations

import uuid

import arrow


def utc_now() -> str:
    return arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")


def normalize_session(session_id: str) -> str:
    """Canonicalize a UUID session id to 32-char lowercase hex (so dash/case differences
    never cause a mismatch). Non-UUID ids (e.g. test names) pass through unchanged."""
    try:
        return uuid.UUID(str(session_id)).hex
    except ValueError, AttributeError, TypeError:
        return session_id
