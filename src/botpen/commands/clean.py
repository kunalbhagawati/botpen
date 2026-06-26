"""``clean`` command (host): remove botpen artifacts - playground folders, docker, the DB.

Host-side: it removes the Hub container itself, so it cannot run inside it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import click

from config import settings

from ..services.scaffolding import docker as docker_service
from .lib.render import box


@click.command()
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
    volumes only; --folders = playground folders; --db = the host DB."""
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
    box(summary, title="clean", style="yellow")
