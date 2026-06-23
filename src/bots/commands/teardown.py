"""``teardown`` command: clean up playground folders + selected Docker components."""

from __future__ import annotations

import click

from ..services.scaffolding import docker as docker_service
from .console import console


@click.command()
@click.option(
    "--docker:components",
    "docker_components",
    default="containers,images,volumes",
    help="comma list: containers,images,volumes",
)
@click.option(
    "--docker:stopped-only",
    "docker_stopped_only",
    is_flag=True,
    help="only stopped botpen containers",
)
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def teardown(docker_components: str, docker_stopped_only: bool, yes: bool) -> None:
    """Clean up: playground folders + the selected docker components (containers/images/volumes)."""
    components = [c.strip() for c in docker_components.split(",") if c.strip()]
    if not yes:
        click.confirm(
            f"Remove playground folders and docker components {components}?",
            abort=True,
        )
    result = docker_service.teardown(components, docker_stopped_only)
    console.print(result)
