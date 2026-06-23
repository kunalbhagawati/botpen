"""SQLModel engine, session, and schema lifecycle for the mailbox.

The schema is owned by Alembic migrations (`migrations/`), generated from the SQLModel models
in :mod:`bots.core.models`. `setup_db()` (exposed as `db setup`) applies them; callers never
touch Alembic directly. SQLite serializes writes itself (WAL + busy_timeout), so callers never
manage a lock. The code is deliberately SQLite-specific - swap the engine/pragmas here when the
backend changes.
"""

from __future__ import annotations

from functools import wraps

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

# pyrefly: ignore [missing-import]
from config import settings

_engine = create_engine(f"sqlite:///{settings.DB_PATH}")


def register_models() -> None:
    """Import the table models so they register on ``SQLModel.metadata`` (needed by reset/drop
    and by Alembic). An explicit call rather than a bare side-effect import."""
    from . import models  # noqa: F401


register_models()


@event.listens_for(_engine, "connect")
def _connection_pragmas(dbapi_conn, _record) -> None:
    """Per-connection SQLite pragmas. SQLite resets these on every connect, and every CLI
    invocation is a fresh process, so FK enforcement and the busy timeout must be re-applied
    per connection - not at `db setup`."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA busy_timeout=30000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def session() -> DBSession:
    """A new SQLModel session bound to the engine (use as a context manager)."""
    return DBSession(_engine)


def transactional(fn):
    """Run `fn` inside a session, injected as its first argument. Commits on success, closes
    after; an exception propagates with the transaction rolled back.

        @transactional
        def write(s, ...): ...

    Callers invoke `write(...)` - the session is supplied by the decorator, not the caller.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with session() as s:
            result = fn(s, *args, **kwargs)
            s.commit()
            return result

    return wrapper


def _alembic_config() -> Config:
    # script_location resolves via alembic.ini's %(here)s; the DB url is built in
    # migrations/env.py from settings - the same source of truth as the app.
    return Config(str(settings.WORKING_DIR / "alembic.ini"))


def _setup() -> None:
    """One-time, persistent engine setup, run before migrations on `db setup`: switch the SQLite
    file to WAL. WAL persists in the file header, so it is set once here rather than per
    connection. (Can't live in a migration - SQLite refuses a journal_mode change inside a
    transaction, and Alembic runs each migration in one.)"""
    with _engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")


def setup_db() -> None:
    """Create the database (if absent), run one-time engine setup (WAL), then apply migrations.
    Idempotent."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _setup()
    command.upgrade(_alembic_config(), "head")


def reset_db() -> None:
    """Drop every table and re-apply migrations from scratch. DESTRUCTIVE."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.drop_all(_engine)
    with _engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    setup_db()
