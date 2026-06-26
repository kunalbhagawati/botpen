"""``scaffold`` command (host): provision one or more isolated agent containers.

Two modes:
- **interactive** (a tty, no ``-n``/``--stack``): ask how many bots, then loop collecting each bot's
  config (model, stack, auto-proceed, auto-start) - cuttable with Ctrl-C; the usual K-vs-N mapping
  then applies (fewer configs than bots -> round-robin, equal -> 1:1, more -> truncate).
- **non-interactive**: ``-n`` + ``--stack`` (a config of per-bot specs); top-level flags act as
  defaults for fields a spec leaves unset.

scaffold runs entirely on the host. `/shared` setup is delegated to the ``hub`` command (a throwaway
Hub container); the Hub lifecycle (``serve``) belongs to ``start``, not here. By default it opens one
terminal per bot (``--no-attach`` to skip).
"""

from __future__ import annotations

import sys
import time

import click
import questionary

from config import settings

from ..core.db import ensure_db
from ..services.scaffolding import docker as docker_service
from ..services.scaffolding import scaffold as scaffold_service
from ..services.scaffolding import templates as templates_service
from .lib.render import box, console
from .lib.utils import (
    MODEL_CHOICES,
    BotSpec,
    parse_scaffold_config,
    random_slug,
    resolve_stack,
    validate_and_group_stack,
    validate_model,
)


def scaffold_options(fn):
    """Shared provisioning options - reused by both `scaffold` and `start`."""
    opts = [
        click.option("-n", "--num-agents", "num_agents", type=int, default=None, help="number of bots to provision"),
        click.option(
            "--stack",
            "stack_config",
            default=None,
            help="per-bot config: file path, inline JSON, or comma-separated models (e.g. haiku,opus)",
        ),
        click.option(
            "--model",
            default=None,
            type=click.Choice(MODEL_CHOICES),
            help="default model for bots whose spec omits one",
        ),
        click.option(
            "--max-disk", "max_disk", type=int, default=None, help="default disk budget MB (from config if unset)"
        ),
        click.option(
            "--bot-auto-proceed-instructions",
            "bot_auto_proceed",
            is_flag=True,
            help="default: bots proceed through bootstrap -> /start themselves",
        ),
        click.option(
            "--auto-start-bot", "auto_start_bot", is_flag=True, help="default: start claude automatically on spin-up"
        ),
        click.option("--no-attach", "no_attach", is_flag=True, help="do not open a terminal per bot"),
        click.option("--yes", is_flag=True, help="non-interactive: install nothing extra for unset stack categories"),
    ]
    for opt in reversed(opts):
        fn = opt(fn)
    return fn


@click.command()
@scaffold_options
def scaffold(num_agents, stack_config, model, max_disk, bot_auto_proceed, auto_start_bot, no_attach, yes) -> None:
    """Scaffold one or more isolated agent playgrounds."""
    ensure_db()  # self-heal the schema if it was wiped (e.g. db teardown)
    specs = _resolve_specs(num_agents, stack_config, model, max_disk, bot_auto_proceed, auto_start_bot, yes)
    _assign_slugs(specs)

    total = len(specs)
    for i, spec in enumerate(specs, start=1):
        console.rule(f"[bold blue]Provisioning bot {i}/{total}: agent-{spec.slug}[/bold blue]")
        container = _provision_one(spec)
        if not no_attach:
            docker_service.open_terminal(container)


# ---------------------------------------------------------------------------
# Spec resolution
# ---------------------------------------------------------------------------


def _resolve_specs(num_agents, stack_config, model, max_disk, bot_auto_proceed, auto_start_bot, yes) -> list[BotSpec]:
    interactive = stack_config is None and num_agents is None and not yes and sys.stdin.isatty()
    specs = _interactive_specs() if interactive else _config_specs(stack_config, num_agents)
    return [_with_defaults(s, model, max_disk, bot_auto_proceed, auto_start_bot) for s in specs]


def _config_specs(stack_config: str | None, num_agents: int | None) -> list[BotSpec]:
    """Non-interactive: parse --stack (or a single default bot), then map K configs to N bots."""
    if stack_config:
        specs = parse_scaffold_config(stack_config)
        for s in specs:
            validate_model(s.model)
    else:
        specs = [BotSpec()]  # one default bot
    n = num_agents if num_agents is not None else len(specs)
    if n < 1:
        raise click.BadParameter("must be >= 1", param_hint="--num-agents")
    return _map_specs(specs, n)


def _interactive_specs() -> list[BotSpec]:
    """Ask N, then collect per-bot configs (cuttable), and map them to N bots."""
    n = click.prompt("how many bots", type=int, default=1)
    if n < 1:
        raise click.BadParameter("must be >= 1", param_hint="num bots")
    collected: list[BotSpec] = []
    for i in range(n):
        console.rule(f"config for bot {i + 1}/{n}  [dim](Ctrl-C to stop adding)[/dim]")
        spec = _prompt_one_spec()
        if spec is None:
            break
        collected.append(spec)
    if not collected:
        raise click.BadParameter("no bot configs given")
    return _map_specs(collected, n)


def _prompt_one_spec() -> BotSpec | None:
    """Prompt one bot's config. Returns None if the operator cancels (Ctrl-C)."""
    model = questionary.select("model?", choices=MODEL_CHOICES, default="default").ask()
    if model is None:
        return None
    stack = resolve_stack({}, interactive=True)
    stack_items = [k for keys in stack.values() for k in keys]
    bot_auto_proceed = bool(questionary.confirm("bot auto-proceeds bootstrap -> /start itself?", default=False).ask())
    auto_start_bot = bool(questionary.confirm("auto-start claude on spin-up?", default=False).ask())
    return BotSpec(
        model=model, stack_items=stack_items, bot_auto_proceed=bot_auto_proceed, auto_start_bot=auto_start_bot
    )


def _map_specs(specs: list[BotSpec], n: int) -> list[BotSpec]:
    """Map K specs onto N bots: equal -> 1:1, fewer -> round-robin, more -> truncate."""
    k = len(specs)
    if k == n:
        return list(specs)
    if k < n:
        return [specs[i % k] for i in range(n)]
    return specs[:n]


def _with_defaults(spec: BotSpec, model, max_disk, bot_auto_proceed, auto_start_bot) -> BotSpec:
    """Fill a spec's unset fields from the top-level flag defaults."""
    return BotSpec(
        model=spec.model if spec.model != "default" else (model or "default"),
        stack_items=spec.stack_items,
        slug=spec.slug,
        max_disk=spec.max_disk if spec.max_disk is not None else max_disk,
        bot_auto_proceed=spec.bot_auto_proceed or bot_auto_proceed,
        auto_start_bot=spec.auto_start_bot or auto_start_bot,
    )


def _assign_slugs(specs: list[BotSpec]) -> None:
    """Give every spec a slug, distinct within this run (random readable words for unset ones)."""
    used: set[str] = {s.slug for s in specs if s.slug}
    for spec in specs:
        if spec.slug:
            continue
        slug = random_slug()
        while slug in used:
            slug = random_slug()
        spec.slug = slug
        used.add(slug)


# ---------------------------------------------------------------------------
# Provisioning one bot
# ---------------------------------------------------------------------------


def _provision_one(spec: BotSpec) -> str:
    """Mint a scaffold, render + build + run its container. Returns the container name."""
    name = f"agent-{spec.slug}"
    max_disk = spec.max_disk or settings.SCAFFOLD_DEFAULT_MAX_DISK_MB
    languages, dbs, tools = validate_and_group_stack(spec.stack_items)
    stack = {"language": list(languages), "db": list(dbs), "tools": list(tools)}

    sc = scaffold_service.create_scaffold(name, max_disk, stack)
    # Durable, scaffold-level folder: epoch.scaffold_id.slug (session_id is per-incarnation and
    # unknown at scaffold time, so it is not part of the folder name).
    dest = settings.WORKING_DIR / "playgrounds" / f"{int(time.time() * 1000)}.{sc['scaffold_id']}.{name}"
    data = {
        "slug": name,
        "scaffold_id": sc["scaffold_id"],
        "uid": sc["uid"],
        "gid": sc["gid"],
        "max_disk_mb": max_disk,
        "apk_packages": " ".join(templates_service.stack_packages(stack)),
        "installed": ", ".join(k for keys in stack.values() for k in keys) or "nothing extra (a blank Alpine base)",
        "oauth_token": settings.CLAUDE_CODE_OAUTH_TOKEN,
        "base_image": settings.SCAFFOLD_BASE_IMAGE,
        "daemon_host": "hub",  # the agent reaches the Hub by name on the shared botpen network
        "daemon_thrift_port": settings.DAEMON_PORT,
        "daemon_ws_port": settings.DAEMON_WS_PORT,
        "shared_volume": settings.SHARED_VOLUME_NAME,
        "agent_user": "agent",
        "bot_auto_proceed": spec.bot_auto_proceed,
        "auto_start_bot": spec.auto_start_bot,
        "bot_model": spec.model if spec.model != "default" else settings.SCAFFOLD_DEFAULT_MODEL,
    }
    templates_service.render(dest, data)
    templates_service.stage_build_inputs(dest, sc["secret_key"])

    container = f"botpen-{name}"
    console.print(f"  building [bold]{container}[/bold] (first build pulls + compiles, give it a minute) ...")
    docker_service.ensure_shared_volume()
    docker_service.ensure_agent_dir(sc["scaffold_id"], sc["uid"], sc["gid"])
    docker_service.build_and_up(dest)
    scaffold_service.set_status(sc["scaffold_id"], "running", container_name=container)
    box(
        f"[green]running[/green] [bold]{container}[/bold]\n"
        f"scaffold: [dim]{sc['scaffold_id']}[/dim]\n"
        f"stack: {stack}\n"
        f"uid/gid: {sc['uid']}   disk: {max_disk}MB   model: {data['bot_model']}\n"
        f"auto-start: {spec.auto_start_bot}   auto-proceed: {spec.bot_auto_proceed}",
        title=f"scaffold {name}",
        style="green",
    )
    return container
