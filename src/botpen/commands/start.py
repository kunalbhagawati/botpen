"""``start`` command (host): set up the DB + Hub, then provision agents.

Thin wrapper over `scaffold`: it guarantees the database and the Hub container are up, then delegates
provisioning (interactive or via ``--stack``) to the scaffold command. ``--no-serve`` skips bringing
the Hub up (assume it is already running).
"""

from __future__ import annotations

import click

from ..core.db import setup_db
from ..services import hub as hub_service
from .scaffold import scaffold, scaffold_options


@click.command()
@scaffold_options
@click.option("--no-serve", "no_serve", is_flag=True, help="don't bring the Hub container up (assume it's running)")
def start(
    num_agents, stack_config, model, max_disk, bot_auto_proceed, auto_start_bot, no_attach, yes, no_serve
) -> None:
    """Set up the DB + Hub, then provision agent(s) (see `scaffold` for the provisioning options)."""
    setup_db()  # idempotent: alembic no-ops when already at head
    if not no_serve:
        hub_service.ensure_hub()
    assert scaffold.callback is not None
    scaffold.callback(
        num_agents=num_agents,
        stack_config=stack_config,
        model=model,
        max_disk=max_disk,
        bot_auto_proceed=bot_auto_proceed,
        auto_start_bot=auto_start_bot,
        no_attach=no_attach,
        yes=yes,
    )
