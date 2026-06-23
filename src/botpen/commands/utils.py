"""CLI-layer parsing/rendering helpers shared across the command groups.

Connection/path resolution lives in :mod:`botpen.core.db` and ``config.settings``; this module
is just CLI input coercion and output rendering.
"""

from __future__ import annotations

import json

import click


def coerce_body(raw: str):
    """BODY is a string or JSON. If it parses as JSON, store it as that JSON value;
    otherwise store it as a plain string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_extra(extra: str | None):
    if extra is None:
        return None
    try:
        return json.loads(extra)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"--extra must be valid JSON: {e}") from e


def render_body(body) -> str:
    return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
