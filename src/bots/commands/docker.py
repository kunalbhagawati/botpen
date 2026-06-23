"""``docker`` command group (operator): Docker lifecycle for scaffolded agents."""

from __future__ import annotations

import click

from ..services.scaffolding import docker as docker_service
from .console import console


@click.group()
def docker() -> None:
    """Docker lifecycle for scaffolded agents."""


@docker.command()
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def prune(yes: bool) -> None:
    """Remove EVERYTHING botpen created: all containers, images, the shared volume, and playground
    folders. Leaves the database (use `db setup --reset` to wipe that)."""
    if not yes:
        click.confirm("Remove all botpen containers, images, the shared volume, and playgrounds?", abort=True)
    result = docker_service.prune_all()
    console.print(f"[green]pruned[/green] {result}")


docker.add_command(prune)
