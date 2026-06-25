"""Root Click group: mounts the command groups as subcommands.

Invoked via the repo-root ``manage.py`` - e.g. ``uv run manage.py db setup``.
The groups themselves live one-per-module under ``commands/``.
"""

from __future__ import annotations

import click

from .commands.db import db
from .commands.permissions import permissions
from .commands.scaffold import scaffold
from .commands.serve import serve


@click.group()
def cli() -> None:
    """botpen - agent sandbox control plane (db / permissions / serve / scaffold). Cleanup is `uv run playground clean`."""


cli.add_command(db)
cli.add_command(permissions)
cli.add_command(serve)
cli.add_command(scaffold)
