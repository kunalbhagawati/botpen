"""``playground`` command group: multi-agent provisioning shortcuts.

``playground start`` spins up N agents in one shot, cycling through a scaffold
config list and provisioning each with auto_start_bot=True + bot_auto_proceed=True.
"""

from __future__ import annotations

import shutil
from itertools import cycle
from pathlib import Path

import click

from ..core.db import setup_db
from config import settings

from ..services.scaffolding import docker as docker_service
from .render import box, console, print_plan
from .scaffold import scaffold
from .utils import parse_scaffold_config, validate_and_group_stack, validate_model


# ---------------------------------------------------------------------------
# Command group + start subcommand
# ---------------------------------------------------------------------------


@click.group()
def playground() -> None:
    """Multi-agent provisioning shortcuts."""


@playground.command()
def setup() -> None:
    """Create the DB (host ./.db/messages.db) and apply migrations (alembic upgrade head). Idempotent."""

    setup_db()
    box("[green]DB ready[/green] - schema at head", title="playground setup", style="green")


@playground.command()
@click.option("--folders", "rm_folders", is_flag=True, help="remove playground folders")
@click.option("--db", "rm_db", is_flag=True, help="remove the DB (.db/messages.db + sidecars)")
@click.option("--docker", "rm_docker", is_flag=True, help="remove all docker: containers + images + volumes")
@click.option(
    "--docker:containers", "rm_docker_containers", is_flag=True, help="remove containers + images (not volumes)"
)
@click.option("--docker:volumes", "rm_docker_volumes", is_flag=True, help="remove volumes only")
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def clean(
    rm_folders: bool, rm_db: bool, rm_docker: bool, rm_docker_containers: bool, rm_docker_volumes: bool, yes: bool
) -> None:
    """Remove botpen artifacts. Default (no flags) = --folders --docker. --docker = all docker
    (containers + images + volumes); --docker:containers = containers + images; --docker:volumes =
    volumes only; --folders = playground folders; --db = the host DB. Host-side - it removes the Hub
    container itself, so it can't run inside it."""
    if not any([rm_folders, rm_db, rm_docker, rm_docker_containers, rm_docker_volumes]):
        rm_folders = rm_docker = True  # default: folders + all docker

    components: list[str] = []
    if rm_docker or rm_docker_containers:
        components += ["containers", "images"]
    if rm_docker or rm_docker_volumes:
        components.append("volumes")

    parts: list[str] = []
    if rm_folders:
        parts.append("playground folders")
    if components:
        parts.append(f"docker [{', '.join(components)}]")
    if rm_db:
        parts.append("the database")
    if not yes:
        click.confirm(f"Remove {', '.join(parts)}?", abort=True)

    result: dict = {}
    if components:
        result.update(docker_service.teardown(components))
    if rm_folders:
        playgrounds = settings.WORKING_DIR / "playgrounds"
        pg = sum(1 for p in playgrounds.iterdir() if p.is_dir()) if playgrounds.exists() else 0
        if playgrounds.exists():
            for p in playgrounds.iterdir():
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
        result["folders"] = pg
    if rm_db:
        db = Path(settings.DB_PATH)
        for p in db.parent.glob(db.name + "*"):  # messages.db + journal sidecars
            p.unlink(missing_ok=True)
        result["db"] = str(settings.DB_PATH)
    summary = "\n".join(f"[bold]{k}[/bold]: {v}" for k, v in result.items()) or "[dim]nothing to remove[/dim]"
    box(summary, title="playground clean", style="yellow")


@playground.command()
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
