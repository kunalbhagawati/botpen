"""SQLModel engine, session, and schema lifecycle for the mailbox.

The schema is owned by Alembic migrations (`migrations/`), generated from the SQLModel models
in :mod:`botpen.core.models`. `setup_db()` (exposed as `db setup`) applies them; callers never
touch Alembic directly. SQLite serializes writes itself (WAL + busy_timeout), so callers never
manage a lock. The code is deliberately SQLite-specific - swap the engine/pragmas here when the
backend changes.
"""

from __future__ import annotations

from functools import wraps

from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect
from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

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


def with_session(fn):
    """Run `fn` inside a session, injected as its first argument; no commit. The base session
    boundary - reads use it directly, writes layer `atomic` on top.

        @with_session
        def read(s, ...): ...

    The `session()` context manager closes on exit, which ends (rolls back) the transaction, so
    reads need nothing extra. Ending it promptly keeps SQLite's WAL checkpointer unblocked (a
    lingering read txn can grow the WAL unbounded). On an exception the close rolls back, so an
    uncommitted write is discarded and the error propagates."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with session() as s:
            return fn(s, *args, **kwargs)

    return wrapper


def atomic(fn):
    """Run a write `fn` inside a session and commit on success. Built on `with_session`, so the
    session lifecycle (and rollback-on-exception via the context-manager close) is shared - this
    only adds the commit.

        @atomic
        def write(s, ...): ...
    """

    @with_session
    @wraps(fn)
    def wrapped(s, *args, **kwargs):
        result = fn(s, *args, **kwargs)
        s.commit()
        return result

    return wrapped


def _alembic_config() -> Config:
    # script_location resolves via alembic.ini's %(here)s; the DB url is built in
    # migrations/env.py from settings - the same source of truth as the app.
    return Config(str(settings.WORKING_DIR / "alembic.ini"))


def _setup() -> None:
    """One-time, persistent engine setup, run before migrations on `db setup`: set the SQLite
    journal mode to DELETE (the classic rollback journal). NOT WAL: the DB file is bind-mounted to
    the host so file-based explorers (DBCode / DataGrip) can open it, and WAL's mmap'd `-shm` does
    not work over the Docker Desktop virtiofs bind, whereas the rollback journal does. (Can't live
    in a migration - SQLite refuses a journal_mode change inside Alembic's per-migration txn.)"""
    with _engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=DELETE")


def setup_db() -> None:
    """Create the database (if absent), run one-time engine setup (journal mode), then apply
    migrations. Idempotent."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _setup()
    command.upgrade(_alembic_config(), "head")


def ensure_db() -> None:
    """Create + migrate the DB if the schema is absent (e.g. after `teardown --db`), so commands
    that need it (scaffold, serve) self-heal instead of crashing on a missing table. Cheap no-op
    when the schema is already present."""
    if not settings.DB_PATH.exists() or not inspect(_engine).has_table("scaffolds"):
        setup_db()


def teardown_db() -> None:
    """Drop every table and the Alembic version table, leaving an empty DB file. DESTRUCTIVE."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.drop_all(_engine)
    with _engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


def reset_db() -> None:
    """Drop every table and re-apply migrations from scratch. DESTRUCTIVE."""
    teardown_db()
    setup_db()
