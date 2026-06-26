"""``playground`` command group: multi-agent provisioning shortcuts.

``playground start`` spins up N agents in one shot, cycling through a scaffold
config list and provisioning each with auto_start_bot=True + bot_auto_proceed=True.
"""

from __future__ import annotations

import json
import shutil
from itertools import cycle
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from ..stack_catalog import SCAFFOLD_STACK_CATALOG
from .console import box, console
from .scaffold import scaffold
from ..core.db import setup_db
from config import settings

from ..services.scaffolding import docker as docker_service

# ---------------------------------------------------------------------------
# Model choices - single source of truth; scaffold.py uses click.Choice inline
# so we derive the list by introspecting that option rather than duplicating it.
# ---------------------------------------------------------------------------
_MODEL_CHOICES: list[str] = ["opus", "sonnet", "haiku", "default"]


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def _parse_stack_config(raw_stack) -> list[str]:
    """Normalize a ScaffoldStackConfig to a flat list of stack item name strings.

    Accepts:
      - ["python", "redis"]                            -> ["python", "redis"]
      - ["python", {"extra": "cfg"}]                   -> ["python"]  (2-elem [name, config])
      - [{"name": "python", "config": {...}}, ...]     -> ["python", ...]
    """
    names: list[str] = []
    if not isinstance(raw_stack, list):
        return names
    i = 0
    while i < len(raw_stack):
        item = raw_stack[i]
        if isinstance(item, str):
            # Could be a bare name or the first element of a [name, config] pair
            if i + 1 < len(raw_stack) and isinstance(raw_stack[i + 1], dict):
                # [name, config] pair - consume both
                names.append(item)
                # TODO: stack item extra config not yet wired
                i += 2
            else:
                names.append(item)
                i += 1
        elif isinstance(item, dict):
            # {"name": ..., "config": {...}}
            key = item.get("name") or item.get("key")
            if isinstance(key, str):
                names.append(key)
            # TODO: stack item extra config not yet wired
            i += 1
        else:
            i += 1
    return names


def _normalize_item(raw_item) -> tuple[str, list[str]]:
    """Normalize a ScaffoldItemConfig to (model, stack_items).

    Accepts:
      - "haiku"                                         -> ("haiku", [])
      - ["haiku", ["python", "redis"]]                  -> ("haiku", ["python", "redis"])
      - {"model": "haiku", "stack": ["python"]}         -> ("haiku", ["python"])
    """
    if isinstance(raw_item, str):
        return raw_item, []
    if isinstance(raw_item, list) and len(raw_item) >= 1 and isinstance(raw_item[0], str):
        model = raw_item[0]
        stack_raw = raw_item[1] if len(raw_item) >= 2 else []
        return model, _parse_stack_config(stack_raw)
    if isinstance(raw_item, dict):
        model = raw_item.get("model", "default")
        stack_raw = raw_item.get("stack", [])
        return str(model), _parse_stack_config(stack_raw if isinstance(stack_raw, list) else [])
    raise click.BadParameter(f"unrecognized scaffold config item: {raw_item!r}", param_hint="--scaffold-config")


def _parse_scaffold_config(raw: str) -> list[tuple[str, list[str]]]:
    """Parse -c value into a list of (model, stack_items) tuples.

    Resolution order:
      1. If raw names an existing file, read its contents.
      2. Try json.loads. If it yields a list -> array-of-items form.
         If it yields a string, or raises -> treat as comma-separated model names.
    """
    source = raw
    p = Path(raw)
    if p.exists() and p.is_file():
        source = p.read_text()

    try:
        parsed = json.loads(source)
    except json.JSONDecodeError, ValueError:
        parsed = source  # treat as comma-separated string

    if isinstance(parsed, list):
        return [_normalize_item(item) for item in parsed]

    # String path: comma-separated model names
    tokens = str(parsed).split(",")
    return [_normalize_item(tok.strip()) for tok in tokens if tok.strip()]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_model(model: str) -> None:
    if model not in _MODEL_CHOICES:
        raise click.BadParameter(
            f"model {model!r} is not one of {_MODEL_CHOICES}",
            param_hint="--scaffold-config",
        )


def _validate_and_group_stack(stack_items: list[str]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Map stack item names to (languages, dbs, tools) tuples, raising BadParameter for unknowns."""
    languages: list[str] = []
    dbs: list[str] = []
    tools: list[str] = []

    all_keys: dict[str, str] = {}  # key -> category
    for category, entries in SCAFFOLD_STACK_CATALOG.items():
        for entry in entries:
            all_keys[str(entry["key"])] = category

    for item in stack_items:
        cat = all_keys.get(item)
        if cat is None:
            valid = list(all_keys.keys())
            raise click.BadParameter(
                f"stack item {item!r} not found in catalog (valid: {valid})",
                param_hint="--scaffold-config",
            )
        if cat == "language":
            languages.append(item)
        elif cat == "db":
            dbs.append(item)
        elif cat == "tools":
            tools.append(item)

    return tuple(languages), tuple(dbs), tuple(tools)


# ---------------------------------------------------------------------------
# Plan display
# ---------------------------------------------------------------------------


def _print_plan(agent_configs: list[tuple[int, str, list[str], str]], mapping_rule: str) -> None:
    """Print the resolved agent plan as a boxed rich table."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Model", style="bold")
    table.add_column("Stack items")

    for idx, model, stack_items, _ in agent_configs:
        table.add_row(
            str(idx),
            model,
            ", ".join(stack_items) if stack_items else "[dim](none)[/dim]",
        )

    panel = Panel(
        table,
        title=f"[bold]Playground plan[/bold]  ({mapping_rule})",
        border_style="blue",
        padding=(0, 1),
    )
    console.print(panel)


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

    raw_configs = _parse_scaffold_config(scaffold_config)
    if not raw_configs:
        raise click.BadParameter("no valid configs found", param_hint="--scaffold-config")

    # Validate models
    for model, _ in raw_configs:
        _validate_model(model)

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

    _print_plan(agent_specs, mapping_rule)

    # Provision each agent. scaffold.callback is set by @click.command (Optional only in the type).
    assert scaffold.callback is not None
    for i, model, stack_items, _ in agent_specs:
        languages, dbs, tools = _validate_and_group_stack(stack_items)
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
