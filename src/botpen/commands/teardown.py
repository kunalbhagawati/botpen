"""``teardown`` command: clean up playground folders, selected Docker components, and the DB.

Runs host-side (it removes the Hub container itself, so it can't run inside it)."""

from __future__ import annotations

import subprocess

import click

from ..services.scaffolding import docker as docker_service
from .console import console

DB_VOLUME = "botpen-db"


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
@click.option("--db", "wipe_db", is_flag=True, help=f"also remove the DB volume ({DB_VOLUME})")
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def teardown(docker_components: str, docker_stopped_only: bool, wipe_db: bool, yes: bool) -> None:
    """Clean up: playground folders + the selected docker components (containers/images/volumes,
    plus the Hub container and the botpen network), and optionally the DB volume."""
    components = [c.strip() for c in docker_components.split(",") if c.strip()]
    if not yes:
        target = f"playground folders and docker components {components}"
        if wipe_db:
            target += f" AND the DB volume ({DB_VOLUME})"
        click.confirm(f"Remove {target}?", abort=True)
    result = docker_service.teardown(components, docker_stopped_only)
    if wipe_db:
        # The Hub container (which mounts this volume) was removed by docker_service.teardown above,
        # so the volume is now free to delete.
        subprocess.run(["docker", "volume", "rm", "-f", DB_VOLUME], capture_output=True)
        result["db_volume"] = DB_VOLUME
    console.print(result)
