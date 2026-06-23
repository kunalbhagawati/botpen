"""SQLModel table models for the agent mailbox - the single source of truth for the schema.

The canonical agent identity is `scaffold_id` (host-minted, durable, survives claude restarts):
every message/thought/permission/request keys on it. A `Session` is one incarnation running
inside a scaffold - a scaffold has 0..N over its life (restarts, and future child/clone agents
that carry the workspace forward under a new personality). The claude transcript id is the
session_id; it is lineage metadata, never the operating key.

JSON-bearing columns use SQLAlchemy's `JSON` type (`sa_column=Column(JSON)`), so the service
layer stores/reads plain Python objects - no manual json-encoding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class StoppedReason(StrEnum):
    """Why an incarnation ended. Stored as the string value on `Session`."""

    COMPLETED = "completed"  # wound down normally / hit its hard stops
    DISK_LIMIT = "disk_limit"  # auto-terminated at 100% of its disk budget
    USER_STOPPED = "user_stopped"  # an operator stopped it
    ERROR = "error"  # crashed / errored out
    OTHER = "other"  # see stopped_reason_notes


class Scaffold(SQLModel, table=True):
    """The durable agent: one container + its private volume. `scaffold_id` is the canonical
    identity used everywhere. Created at `scaffold new` time, before any claude session exists;
    `secret_key` is the per-agent token the daemon authenticates."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "scaffolds"

    scaffold_id: str = Field(primary_key=True)  # uuid hex, host-minted - the canonical agent id
    scaffold_slug: str  # human name; the /shared/<slug>/ dir + container name
    created_at: str
    secret_key: str = Field(unique=True, index=True)  # per-agent token (the daemon's auth lookup)
    uid: int
    gid: int
    max_disk_mb: int
    stack: Any | None = Field(default=None, sa_column=Column(JSON))  # host-provisioned stack (catalog selection)
    image_tag: str | None = None
    container_name: str | None = None
    status: str = "created"  # created | running | stopped | failed


class Session(SQLModel, table=True):
    """One incarnation (a claude transcript) running inside a scaffold. Carries the personality
    and lifecycle of that run; multiple sessions can share a scaffold over time (lineage)."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "sessions"

    session_id: str = Field(primary_key=True)  # claude transcript uuid (lineage metadata)
    scaffold_id: str | None = Field(default=None, foreign_key="scaffolds.scaffold_id", index=True)
    registered_at: str
    model: str | None = None
    description: str | None = None
    agent_personality: str | None = None  # one-line self-description for this incarnation
    chosen_stack: Any | None = Field(default=None, sa_column=Column(JSON))  # free-form, agent-maintained
    thoughts_readers: list[str] | None = Field(default=None, sa_column=Column(JSON))  # session_ids allowed to read

    # Lifecycle end of this incarnation.
    stopped_at: str | None = None
    stopped_reason: str | None = None  # a StoppedReason value
    stopped_reason_notes: str | None = None
    stopped_sig: str | None = None  # terminating signal name, e.g. "SIGTERM"


class Message(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    scaffold_id: str = Field(foreign_key="scaffolds.scaffold_id", index=True)  # the durable agent (lineage)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)  # the incarnation that sent it
    created_at: str
    msg: Any = Field(sa_column=Column(JSON, nullable=False))  # the body (any JSON value)
    extra: Any | None = Field(default=None, sa_column=Column(JSON))
    to: list[str] | None = Field(default=None, sa_column=Column(JSON))  # recipient scaffold ids; NULL = everyone


class Thought(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "thoughts"

    id: int | None = Field(default=None, primary_key=True)
    scaffold_id: str = Field(foreign_key="scaffolds.scaffold_id", index=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)  # the incarnation
    created_at: str
    thoughts: str
    extra: Any | None = Field(default=None, sa_column=Column(JSON))


class PermissionLog(SQLModel, table=True):
    """Append-only audit log of host-mediated shared-volume permission actions.

    `grant` holds the request as a JSON tree; each node is
    `{"path": str, "is_recursive": bool, "permissions": str, "children": [...]}`.
    """

    # pyrefly: ignore [bad-override]
    __tablename__ = "permission_log"

    id: int | None = Field(default=None, primary_key=True)
    permission_type: str  # ask | grant | revoke
    owner_scaffold_id: str = Field(foreign_key="scaffolds.scaffold_id", index=True)  # whose /shared folder
    peer_scaffold_id: str = Field(foreign_key="scaffolds.scaffold_id", index=True)  # the other agent
    grant: Any | None = Field(default=None, sa_column=Column(JSON))  # tree of {path, is_recursive, permissions, children}
    peer_permission_request_reason: str | None = None
    owner_permission_decision_reason: str | None = None
    status: str  # requested | applied | revoked | failed
    error: str | None = None
    created_at: str
    updated_at: str
    applied_at: str | None = None


class RequestLog(SQLModel, table=True):
    """Every request the daemon serves, for debugging/audit (Thrift's binary RPC is not
    curl-debuggable). The token is stored only if REQUEST_LOG_REDACT_TOKEN is off (default)."""

    # pyrefly: ignore [bad-override]
    __tablename__ = "request_log"

    id: int | None = Field(default=None, primary_key=True)
    created_at: str
    method: str
    scaffold_id: str | None = Field(default=None, index=True)  # resolved caller (no FK: log table)
    request: Any | None = Field(default=None, sa_column=Column(JSON))
    status: str  # ok | error
    error: str | None = None
    duration_ms: int | None = None
