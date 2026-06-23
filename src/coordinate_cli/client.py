"""Thin synchronous Thrift client to the host Hub daemon.

The agent's identity (its scaffold's secret token) is baked into the binary (`_identity.TOKEN`)
and attached to every call HERE - the agent never sees, passes, or even knows about it. Auth is
strictly between the binary and the Hub. Connection host/port come from env (non-secret config).
"""

from __future__ import annotations

import json
import os
from typing import Any

from thriftpy2.rpc import make_client

from . import _identity
from .idl import hub


def host_port() -> tuple[str, int]:
    host = os.environ.get("COORDINATE__HOST", "host.docker.internal")
    port = int(os.environ.get("COORDINATE__THRIFT_PORT", "8787"))
    return host, port


def token() -> str:
    """The baked-in secret token. Falls back to the COORDINATE__TOKEN env var in dev (unbaked)."""
    tok = _identity.TOKEN or os.environ.get("COORDINATE__TOKEN", "")
    if not tok:
        raise SystemExit("no baked identity (rebuild via `scaffold new`)")
    return tok


def call(method: str, *args: Any) -> Any:
    """Open a client, invoke `method(token, *args)`, parse the JSON reply, close. The token is
    injected here - callers pass only the method's real arguments."""
    host, port = host_port()
    client = make_client(hub().Hub, host, port)
    try:
        raw = getattr(client, method)(token(), *args)
        return json.loads(raw) if raw else None
    finally:
        client.close()


def coerce_body(text: str) -> str:
    """Agent body is text or JSON. Return a JSON-encoded string for the wire (the daemon decodes
    it): if `text` already parses as JSON, keep that value; otherwise treat it as a plain string."""
    try:
        return json.dumps(json.loads(text))
    except (ValueError, TypeError):
        return json.dumps(text)
