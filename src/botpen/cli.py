"""Root Click group for the host `botpen` command: mounts the command modules as subcommands.

Invoked via the repo-root ``botpen`` shebang or the ``botpen`` console script - e.g.
``botpen db setup`` / ``botpen scaffold`` / ``botpen start``. The groups themselves live
one-per-module under ``commands/``. The in-Hub-container surface is the separate ``hub`` command
(:mod:`botpen.hub`); the agent surface is ``coordinate`` (:mod:`coordinate_cli`).
"""

from __future__ import annotations

import click

from .commands.clean import clean
from .commands.db import db
from .commands.permissions import permissions
from .commands.scaffold import scaffold
from .commands.serve import serve
from .commands.start import start


@click.group()
def cli() -> None:
    """botpen - host operator CLI: provision and run agents, serve the Hub, manage the DB, audit, clean up."""


cli.add_command(start)
cli.add_command(scaffold)
cli.add_command(serve)
cli.add_command(clean)
cli.add_command(db)
cli.add_command(permissions)
