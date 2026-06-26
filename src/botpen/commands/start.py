"""``start`` command (host): multi-agent provisioning shortcut.

`start` spins up N agents in one shot, cycling through a scaffold config list and provisioning each
with auto_start_bot=True + bot_auto_proceed=True.
"""

from __future__ import annotations

from itertools import cycle

import click

from ..core.db import setup_db
from .lib.render import console, print_plan
from .lib.utils import parse_scaffold_config, validate_and_group_stack, validate_model
from .scaffold import scaffold


@click.command()
@click.option("-n", "--num-agents", "num_agents", required=True, type=int, help="number of agents to provision")
@click.option(
    "-c",
    "--scaffold-config",
    "scaffold_config",
    required=True,
    help="JSON file path, inline JSON array, or comma-separated model names (e.g. haiku,opus,sonnet)",
)
def start(num_agents: int, scaffold_config: str) -> None:
    """Provision N agents from a scaffold config, all with auto-start enabled."""
    if num_agents < 1:
        raise click.BadParameter("must be >= 1", param_hint="--num-agents")

    # Ensure the DB + schema exist before provisioning (idempotent: alembic no-ops when at head).
    setup_db()

    raw_configs = parse_scaffold_config(scaffold_config)
    if not raw_configs:
        raise click.BadParameter("no valid configs found", param_hint="--scaffold-config")

    # Validate models
    for model, _ in raw_configs:
        validate_model(model)

    # Map configs -> N agents (1:1, round-robin, or truncate)
    n = len(raw_configs)
    if n == num_agents:
        mapping_rule = "1:1 mapping"
        assigned = list(raw_configs)
    elif n < num_agents:
        mapping_rule = f"round-robin ({n} config(s) -> {num_agents} agents)"
        assigned = [c for _, c in zip(range(num_agents), cycle(raw_configs))]
    else:
        mapping_rule = f"truncated (first {num_agents} of {n} configs)"
        assigned = raw_configs[:num_agents]

    # Build full agent spec list: (index, model, stack_items, display_rule)
    agent_specs: list[tuple[int, str, list[str], str]] = []
    for i, (model, stack_items) in enumerate(assigned, start=1):
        agent_specs.append((i, model, stack_items, mapping_rule))

    print_plan(agent_specs, mapping_rule)

    # Provision each agent. scaffold.callback is set by @click.command (Optional only in the type).
    assert scaffold.callback is not None
    for i, model, stack_items, _ in agent_specs:
        languages, dbs, tools = validate_and_group_stack(stack_items)
        console.rule(f"[bold blue]Provisioning agent {i}/{num_agents}[/bold blue]")
        scaffold.callback(
            slug=None,
            max_disk=None,
            languages=languages,
            dbs=dbs,
            tools=tools,
            no_attach=False,
            bot_auto_proceed=True,
            auto_start_bot=True,
            model=model if model != "default" else None,
            no_serve=False,
            yes=True,
        )
