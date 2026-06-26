"""``permissions`` command group (operator audit view).

Operators inspect the append-only permission log written by the hub daemon.
Agents interact with the hub via the ``manage`` binary, not this CLI group.
"""

from __future__ import annotations

import json

import click
from rich.table import Table

from ..services import permissions as permissions_service
from .render import console


@click.group()
def permissions() -> None:
    """Shared-volume permission log (operator audit view)."""


@click.command("list")
@click.option("--scaffold", "scaffold_id", default=None, help="filter to rows involving this scaffold")
@click.option("--json", "as_json", is_flag=True, help="emit JSON instead of a table")
def list_log(scaffold_id: str | None, as_json: bool) -> None:
    """List permission-log rows (optionally filtered to one scaffold)."""
    rows = permissions_service.list_log(scaffold_id)
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[dim]no permission-log entries[/dim]")
        return
    title = "permission log" + (f" for {scaffold_id}" if scaffold_id else "")
    table = Table(title=title, show_lines=True)
    for col in ("id", "permission_type", "owner", "peer", "status"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["permission_type"],
            r["owner"],
            r["peer"],
            r["status"],
        )
    console.print(table)


permissions.add_command(list_log)
