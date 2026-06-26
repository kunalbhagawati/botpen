"""``db`` command group: database lifecycle (setup / reset / teardown).

`setup` applies the Alembic migrations - users never invoke Alembic directly.
"""

from __future__ import annotations

import click
from sqlmodel import SQLModel

from config import settings

from ..core import db as core_db


@click.group()
def db() -> None:
    """Database lifecycle: setup / reset / teardown."""


@db.command()
def setup() -> None:
    """Create the database and bring it to the latest migration (idempotent)."""
    core_db.setup_db()
    click.echo(f"db ready at {settings.DB_PATH}")
    click.echo(f"tables: {', '.join(sorted(SQLModel.metadata.tables))}")


@db.command()
def reset() -> None:
    """DROP all tables and re-apply migrations from scratch (DESTRUCTIVE)."""
    core_db.reset_db()
    click.echo("reset: dropped all tables and re-applied migrations")
    click.echo(f"db ready at {settings.DB_PATH}")


@db.command()
def teardown() -> None:
    """DROP all tables, leaving an empty DB file (DESTRUCTIVE)."""
    core_db.teardown_db()
    click.echo(f"teardown: dropped all tables at {settings.DB_PATH}")
