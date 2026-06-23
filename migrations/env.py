"""Alembic environment for the bots mailbox.

Adds the repo root to sys.path (so the root-level `config` is importable however Alembic is
launched), points the DB url at `settings.DB_PATH`, and targets the SQLModel metadata.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# pyrefly: ignore [missing-import]
from config import settings  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from bots.core import models  # noqa: E402, F401  -- registers tables on SQLModel.metadata

config = context.config
config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
