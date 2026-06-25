"""``teardown`` command: clean up playground folders, selected Docker components, and the DB.

Runs host-side (it removes the Hub container itself, so it can't run inside it)."""

from __future__ import annotations

from pathlib import Path

import click

# pyrefly: ignore [missing-import]
from config import settings

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
@click.option("--db", "wipe_db", is_flag=True, help="also remove the DB (.db/messages.db + sidecars)")
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def teardown(docker_components: str, docker_stopped_only: bool, wipe_db: bool, yes: bool) -> None:
    """Clean up: playground folders + the selected docker components (containers/images/volumes,
    plus the Hub container and the botpen network), and optionally the DB.

    The DB is bind-mounted to the host ./.db, so --db removes the host file directly."""
    components = [c.strip() for c in docker_components.split(",") if c.strip()]
    if not yes:
        target = f"playground folders and docker components {components}"
        if wipe_db:
            target += " AND the database"
        click.confirm(f"Remove {target}?", abort=True)
    result = docker_service.teardown(components, docker_stopped_only)
    if wipe_db:
        db = Path(settings.DB_PATH)
        for p in db.parent.glob(db.name + "*"):  # messages.db + any journal sidecars
            p.unlink(missing_ok=True)
        result["db"] = str(settings.DB_PATH)
    console.print(result)
