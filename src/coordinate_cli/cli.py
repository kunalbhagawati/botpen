"""The `coordinate` CLI - the agent's whole command surface, a Thrift client to the Hub daemon.

The agent's identity (its scaffold's secret token) is baked into the binary and attached to every
call inside `client.call` - it is never an argument, an option, or anything the agent passes or
sees. Only `register` takes the agent's own claude session id (the incarnation; not a secret).
"""

from __future__ import annotations

import json
from typing import Any

import click

from . import client, daemons
from .idl import hub


def _grant_node(d: dict) -> Any:
    """Build a (recursive) Thrift GrantNode from a plain dict tree."""
    return hub().GrantNode(
        path=d["path"],
        is_recursive=bool(d.get("is_recursive", False)),
        permissions=d.get("permissions", "rx"),
        children=[_grant_node(c) for c in d.get("children", [])],
    )


@click.group()
def cli() -> None:
    """coordinate - talk to the hub from inside your container."""


@cli.command()
@click.argument("session_id")
@click.option("--model", default="")
@click.option("--description", default="")
@click.option("--personality", default="", help="one line about your personality")
def register(session_id: str, model: str, description: str, personality: str) -> None:
    """Register THIS incarnation (your claude session id) under your scaffold."""
    click.echo(json.dumps(client.call("register_session", session_id, model, description, personality)))


@cli.command()
def ready() -> None:
    """Ping the host that this container is up (called by the entrypoint)."""
    click.echo(json.dumps(client.call("ready")))


@cli.group()
def messages() -> None:
    """Talk to the other agents: send, read, and look them up."""


@messages.command("write")
@click.argument("body")
@click.option("--extra", default="", help="optional JSON attributes")
@click.option("--to", "to_", multiple=True, help="recipient scaffold id; repeat; omit = broadcast")
def messages_write(body: str, extra: str, to_: tuple[str, ...]) -> None:
    """Send a message (broadcast, or --to specific agents). BODY is text or JSON."""
    click.echo(json.dumps(client.call("write", client.coerce_body(body), extra, list(to_))))


@messages.command("read")
def messages_read() -> None:
    """Read messages addressed to you since your last read."""
    click.echo(json.dumps(client.call("read"), indent=2))


@messages.command("about")
@click.argument("scaffold_id")
@click.option("--extra-fields", default="", help="comma list: personality,model")
def messages_about(scaffold_id: str, extra_fields: str) -> None:
    """Look up another agent's public profile."""
    fields = [f for f in extra_fields.split(",") if f]
    click.echo(json.dumps(client.call("about", scaffold_id, fields)))


@cli.command()
@click.argument("thoughts")
@click.option("--extra", default="")
def think(thoughts: str, extra: str) -> None:
    """Record a thought (private unless you grant readers)."""
    click.echo(json.dumps(client.call("think", thoughts, extra)))


@cli.group()
def permissions() -> None:
    """Grant / ask / read access to your files (shared folder) or your thoughts."""


@permissions.group("files")
def perm_files() -> None:
    """Shared-folder access (the host applies the ACL)."""


@perm_files.command("ask")
@click.argument("peer")
@click.option("--why", default="")
def files_ask(peer: str, why: str) -> None:
    """Ask PEER (a scaffold id) to share part of their /shared folder with you."""
    click.echo(json.dumps(client.call("perm_ask", peer, why)))


@perm_files.command("grant")
@click.argument("peer")
@click.option("--path", default=None, help="relpath under your /shared/<slug>/")
@click.option("--recursive", is_flag=True)
@click.option("--perms", default="rx")
@click.option("--grant-json", default=None, help="full grant tree as JSON (overrides --path)")
@click.option("--why", default="")
def files_grant(peer: str, path: str | None, recursive: bool, perms: str, grant_json: str | None, why: str) -> None:
    """Grant PEER (a scaffold id) read access to a path (or JSON tree) in your /shared folder."""
    if grant_json:
        tree = _grant_node(json.loads(grant_json))
    elif path:
        tree = _grant_node({"path": path, "is_recursive": recursive, "permissions": perms})
    else:
        raise click.UsageError("pass --path or --grant-json")
    click.echo(json.dumps(client.call("perm_grant", peer, tree, why)))


@perm_files.command("revoke")
@click.argument("peer")
@click.option("--path", required=True)
@click.option("--why", default="")
def files_revoke(peer: str, path: str, why: str) -> None:
    """Revoke PEER's access to a path in your /shared folder."""
    tree = _grant_node({"path": path, "is_recursive": False, "permissions": ""})
    click.echo(json.dumps(client.call("perm_revoke", peer, tree, why)))


@perm_files.command("list")
def files_list() -> None:
    """List permission-log rows involving you."""
    click.echo(json.dumps(client.call("perm_list"), indent=2))


@permissions.group("thoughts")
def perm_thoughts() -> None:
    """Thought-sharing across incarnations (by session id)."""


@perm_thoughts.command("ask")
@click.argument("owner_session_id")
@click.option("--why", default="")
def thoughts_ask(owner_session_id: str, why: str) -> None:
    """Ask OWNER_SESSION_ID to share their thoughts with you (pushed to them; they decide)."""
    click.echo(json.dumps(client.call("thoughts_ask", owner_session_id, why)))


@perm_thoughts.command("grant")
@click.argument("peer_session_id")
def thoughts_grant(peer_session_id: str) -> None:
    """Let PEER_SESSION_ID read your thoughts."""
    click.echo(json.dumps(client.call("thoughts_grant", peer_session_id)))


@perm_thoughts.command("revoke")
@click.argument("peer_session_id")
def thoughts_revoke(peer_session_id: str) -> None:
    """Stop PEER_SESSION_ID from reading your thoughts."""
    click.echo(json.dumps(client.call("thoughts_revoke", peer_session_id)))


@perm_thoughts.command("read")
@click.argument("owner_session_id")
def thoughts_read(owner_session_id: str) -> None:
    """Read OWNER_SESSION_ID's thoughts (if they granted you)."""
    click.echo(json.dumps(client.call("thoughts_read", owner_session_id), indent=2))


@cli.group()
def stack() -> None:
    """Your chosen-stack document (free-form JSON; we only record it)."""


@stack.command("schema")
def stack_schema() -> None:
    """Get the suggested document shape (you may ignore it)."""
    click.echo(json.dumps(client.call("stack_schema"), indent=2))


@stack.command("get")
def stack_get() -> None:
    """Get your current chosen-stack document."""
    click.echo(json.dumps(client.call("stack_get"), indent=2))


@stack.command("set")
@click.argument("stack_json")
def stack_set(stack_json: str) -> None:
    """Replace your chosen-stack document (STACK_JSON is your JSON)."""
    click.echo(json.dumps(client.call("stack_set", stack_json)))


@cli.command()
def relay() -> None:
    """Background daemon: consume the WebSocket push channel."""
    daemons.relay(client.token())


@cli.command("disk-monitor")
def disk_monitor() -> None:
    """Background daemon: enforce the disk budget (auto-terminate at 100%)."""
    daemons.disk_monitor(client.token())


@cli.command("daemons")
def run_daemons() -> None:
    """Background: run the relay + disk-monitor, restarting them if they exit."""
    daemons.run_daemons(client.token())
