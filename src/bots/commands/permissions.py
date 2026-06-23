"""``permissions`` command group: ask / grant / deny / revoke / list / check."""

from __future__ import annotations

import json

import click
from rich.table import Table

from ..services import permissions as permissions_service
from .console import console


@click.group()
def permissions() -> None:
    """Cross-agent read permissions: ask / grant / deny / revoke / list / check."""


@click.command("ask")
@click.argument("session_id")
@click.argument("granter")
@click.option("--why", help="why you want access")
def ask(session_id: str, granter: str, why: str | None) -> None:
    """Ask GRANTER for read access to their folder (SESSION_ID is you, the asker).

    You do NOT specify paths - you don't know the granter's folder. The granter decides
    what (if anything) to open up.
    """
    permissions_service.ask_permission(session_id, granter, why)
    click.echo(json.dumps({"event": "asked", "asker": session_id, "granter": granter, "status": "requested"}))


@click.command("grant")
@click.argument("session_id")
@click.argument("asker")
@click.option("--paths", required=True, help="JSON array of path strings/globs you open up")
@click.option("--why", help="why you grant / trust them")
def grant(session_id: str, asker: str, paths: str, why: str | None) -> None:
    """Grant ASKER read access to PATHS in your folder (SESSION_ID is you, the granter)."""
    try:
        paths_val = json.loads(paths)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"--paths must be valid JSON (an array of strings): {e}") from e
    if not isinstance(paths_val, list):
        raise click.ClickException("--paths must be a JSON array of strings/globs")
    try:
        permissions_service.grant_permission(session_id, asker, paths_val, why)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    click.echo(json.dumps({"event": "granted", "granter": session_id, "asker": asker, "paths": paths_val}))


@click.command("deny")
@click.argument("session_id")
@click.argument("asker")
@click.option("--reason", help="why you are denying")
def deny(session_id: str, asker: str, reason: str | None) -> None:
    """Deny ASKER's request (SESSION_ID is you, the granter)."""
    n = permissions_service.deny_permission(session_id, asker, reason)
    click.echo(json.dumps({"event": "denied", "granter": session_id, "asker": asker, "rows": n}))


@click.command("revoke")
@click.argument("session_id")
@click.argument("asker")
@click.option("--reason", help="why you are revoking")
def revoke(session_id: str, asker: str, reason: str | None) -> None:
    """Revoke ASKER's previously granted access (SESSION_ID is you, the granter)."""
    n = permissions_service.revoke_permission(session_id, asker, reason)
    click.echo(json.dumps({"event": "revoked", "granter": session_id, "asker": asker, "rows": n}))


@click.command("list")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, help="emit JSON instead of a table")
def list_perms(session_id: str, as_json: bool) -> None:
    """List permissions involving SESSION_ID (as asker and as granter)."""
    rows = permissions_service.list_permissions(session_id)
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[dim]no permissions[/dim]")
        return
    table = Table(title=f"permissions for {session_id}", show_lines=True)
    for col in ("id", "asker", "granter", "status", "paths", "ask_why", "grant_why"):
        table.add_column(col)
    for r in rows:
        paths = json.dumps(r["paths"], ensure_ascii=False) if r["paths"] else ""
        table.add_row(
            str(r["id"]), r["asker"], r["granter"], r["status"], paths, r["ask_why"] or "", r["grant_why"] or ""
        )
    console.print(table)


@click.command("check")
@click.argument("asker")
@click.argument("granter")
@click.option("--path", help="optional specific path to test against the granted globs")
def check(asker: str, granter: str, path: str | None) -> None:
    """Check whether ASKER may read GRANTER's folder (optionally a specific PATH)."""
    click.echo(json.dumps(permissions_service.can_read(asker, granter, path)))


permissions.add_command(ask)
permissions.add_command(grant)
permissions.add_command(deny)
permissions.add_command(revoke)
permissions.add_command(list_perms)
permissions.add_command(check)
