"""``scaffold`` command group: provision a new isolated agent container.

`scaffold new` mints a Scaffold (id + token + uid/gid), resolves the runtime stack (flags, or an
interactive multi-step form), and renders the playground skeleton into `playgrounds/<slug>/`.
Building + running the container is Phase 5.
"""

from __future__ import annotations

import secrets
import sys
import time

import click
import questionary

# pyrefly: ignore [missing-import]
from config import settings

from ..stack_catalog import SCAFFOLD_STACK_CATALOG
from ..services.scaffolding import docker as docker_service
from ..services.scaffolding import scaffold as scaffold_service
from ..services.scaffolding import templates as templates_service
from .console import console


@click.group()
def scaffold() -> None:
    """Provision and manage isolated agent containers."""


def _resolve_stack(flags: dict[str, tuple[str, ...]], interactive: bool) -> dict[str, list[str]]:
    """Resolve each catalog category to a chosen SUBSET: explicit flags, an interactive
    multi-select, or empty (blank Alpine). Iterates the catalog, so new categories appear in the
    form without touching this code."""
    stack: dict[str, list[str]] = {}
    for category, entries in SCAFFOLD_STACK_CATALOG.items():
        keys = [e["key"] for e in entries]
        chosen = list(flags.get(category) or ())
        if not chosen and interactive:
            chosen = questionary.checkbox(f"{category}?", choices=keys).ask() or []
        for k in chosen:
            if k not in keys:
                raise click.BadParameter(f"{category}: '{k}' not in {keys}")
        stack[category] = chosen
    return stack


@scaffold.command("new")
@click.option("--slug", default=None, help="playground name (default: a random agent-XXXXXX)")
@click.option("--max-disk", "max_disk", type=int, default=None, help="disk budget MB (default from config)")
@click.option("--language", "languages", multiple=True, help="language(s) to install (repeatable)")
@click.option("--db", "dbs", multiple=True, help="database(s) to install (repeatable)")
@click.option("--tools", "tools", multiple=True, help="extra tool(s) to install (repeatable)")
@click.option("--no-attach", is_flag=True, help="do not attach a terminal after run")
@click.option("--auto", is_flag=True, help="agent proceeds to /start itself after bootstrap (no human first instruction)")
@click.option("--yes", is_flag=True, help="non-interactive: install nothing extra for unset categories")
def new(slug, max_disk, languages, dbs, tools, no_attach, auto, yes) -> None:
    """Scaffold a new isolated agent playground."""
    slug = slug or f"agent-{secrets.token_hex(3)}"
    max_disk = max_disk or settings.SCAFFOLD_DEFAULT_MAX_DISK_MB
    flags = {"language": languages, "db": dbs, "tools": tools}
    any_flag = any(flags.values())
    interactive = not yes and not any_flag and sys.stdin.isatty()
    stack = _resolve_stack(flags, interactive)

    sc = scaffold_service.create_scaffold(slug, max_disk, stack)
    # Durable, scaffold-level folder: epoch.scaffold_id.slug (session_id is per-incarnation and
    # unknown at scaffold time, so it is not part of the folder name).
    dest = settings.WORKING_DIR / "playgrounds" / f"{int(time.time() * 1000)}.{sc['scaffold_id']}.{slug}"
    data = {
        "slug": slug,
        "scaffold_id": sc["scaffold_id"],
        "secret_key": sc["secret_key"],
        "uid": sc["uid"],
        "gid": sc["gid"],
        "max_disk_mb": max_disk,
        "apk_packages": " ".join(templates_service.stack_packages(stack)),
        "installed": ", ".join(k for keys in stack.values() for k in keys) or "nothing extra (a blank Alpine base)",
        "oauth_token": settings.CLAUDE_CODE_OAUTH_TOKEN,
        "base_image": settings.SCAFFOLD_BASE_IMAGE,
        "daemon_host": "host.docker.internal",
        "daemon_thrift_port": settings.DAEMON_PORT,
        "daemon_ws_port": settings.DAEMON_WS_PORT,
        "shared_volume": settings.SHARED_VOLUME_NAME,
        "agent_user": "agent",
        "auto": auto,
    }
    templates_service.render(dest, data)
    templates_service.stage_build_inputs(dest, sc["secret_key"])
    console.print(f"[green]scaffolded[/green] [bold]{slug}[/bold]  stack={stack}  uid/gid={sc['uid']}  disk={max_disk}MB")

    container = f"botpen-{slug}"
    console.print("  building image + starting container (first build pulls + compiles, give it a minute) ...")
    docker_service.ensure_shared_volume()
    docker_service.ensure_agent_dir(sc["scaffold_id"], sc["uid"], sc["gid"])
    docker_service.build_and_up(dest)
    scaffold_service.set_status(sc["scaffold_id"], "running", container_name=container)
    console.print(f"  [green]running[/green] [bold]{container}[/bold] - register inside with `coordinate register <session-id>`")
    if no_attach:
        console.print(f"  attach with: docker exec -it {container} bash")
    else:
        docker_service.attach(container)


scaffold.add_command(new)
