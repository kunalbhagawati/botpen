"""``db`` command group: database lifecycle (setup / reset).

`setup` applies the Alembic migrations - users never invoke Alembic directly.
"""

from __future__ import annotations

import click
from sqlmodel import SQLModel

# pyrefly: ignore [missing-import]
from config import settings

from ..core import db as core_db


@click.group()
def db() -> None:
    """Database lifecycle for the mailbox (setup / reset)."""


@click.command()
@click.option("--reset", is_flag=True, help="DROP all tables and re-apply migrations (DESTRUCTIVE)")
def setup(reset: bool) -> None:
    """Create the database and bring it to the latest migration (idempotent)."""
    if reset:
        core_db.reset_db()
        click.echo("reset: dropped all tables and re-applied migrations")
    else:
        core_db.setup_db()
    click.echo(f"db ready at {settings.DB_PATH}")
    click.echo(f"tables: {', '.join(sorted(SQLModel.metadata.tables))}")


db.add_command(setup)
