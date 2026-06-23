"""SQLModel table models for the agent mailbox - the single source of truth for the schema.

JSON-bearing columns (`msg`, `extra`, `to`, `paths`) are stored as TEXT; the service layer
json-encodes/decodes them so the stored shape and CLI output stay byte-for-byte as before.
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "sessions"

    session_id: str = Field(primary_key=True)
    registered_at: str
    model: str | None = None
    description: str | None = None
    thoughts: str | None = None
    path: str | None = None


class Message(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "messages"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    ts: str
    msg: str  # JSON body (any JSON value)
    extra: str | None = None  # JSON attributes, or NULL
    to: str | None = None  # JSON array of recipient session ids; NULL = everyone


class Thought(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "thoughts"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    ts: str
    thoughts: str
    extra: str | None = None


class Permission(SQLModel, table=True):
    # pyrefly: ignore [bad-override]
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("asker", "granter"),)

    id: int | None = Field(default=None, primary_key=True)
    asker: str = Field(foreign_key="sessions.session_id")
    granter: str = Field(foreign_key="sessions.session_id", index=True)
    status: str  # 'requested' | 'granted' | 'denied' | 'revoked'
    ask_why: str | None = None
    grant_why: str | None = None
    paths: str | None = None  # JSON array of granted path strings/globs
    revoked_at: str | None = None
    revoked_reason: str | None = None
    created_at: str
    updated_at: str
