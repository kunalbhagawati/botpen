"""Root Click group: mounts the three command groups as subcommands.

Invoked via the repo-root ``manage.py`` - e.g. ``uv run manage.py messages write <me> "hi"``.
The groups themselves live one-per-module under ``commands/``.
"""

from __future__ import annotations

import click

from .commands.db import db
from .commands.messages import messages
from .commands.permissions import permissions


@click.group()
def cli() -> None:
    """bots - SQLite-backed agent mailbox (messages / db / permissions)."""


cli.add_command(messages)
cli.add_command(db)
cli.add_command(permissions)
