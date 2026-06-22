"""click CLI for the SQLite-backed agent mailbox.

Commands:
    messages register <session-id> [--other ...] [--telemetry ...] [--params ...]
    messages write    <session-id> [--m TEXT]      # TEXT may be multiline; omit to read stdin
    messages read     <session-id> [--json]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import db

_console = Console()


def _root() -> Path:
    return Path(os.environ.get("MESSAGES_ROOT", Path.cwd())).resolve()


def _db_path() -> Path:
    root = _root()
    load_dotenv(root / ".env")
    raw = os.environ.get("MESSAGES_DB", "messages.db")
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (root / p)


def _connect():
    return db.connect(_db_path())


@click.group()
def main() -> None:
    """SQLite-backed agent mailbox (init / register / write / read)."""


@main.command()
@click.option("--reset", is_flag=True, help="DROP existing tables and recreate them (DESTRUCTIVE)")
def init(reset: bool) -> None:
    """Create the SQLite database and tables (idempotent)."""
    db_path = _db_path()
    conn = db.connect(db_path)  # connect() already creates tables if absent
    if reset:
        db.reset(conn)
        click.echo("reset: dropped and recreated tables")
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    click.echo(f"db ready at {db_path}")
    click.echo(f"tables: {', '.join(tables)}")


@main.command()
@click.argument("session_id")
@click.option("--other", help="freeform/JSON: related sessions or counterparties")
@click.option("--telemetry", help="freeform/JSON: telemetry blob")
@click.option("--params", help="freeform/JSON: session parameters")
def register(session_id: str, other: str | None, telemetry: str | None, params: str | None) -> None:
    """Register or update SESSION_ID's metadata."""
    db.register(_connect(), session_id, other, telemetry, params)
    click.echo(f"registered {session_id}")


@main.command()
@click.argument("session_id")
@click.option("--m", "-m", "--message", "message", help="message body (single or multiline); omit to read stdin")
def write(session_id: str, message: str | None) -> None:
    """Append a message authored by SESSION_ID."""
    body = message if message is not None else sys.stdin.read()
    body = body.rstrip("\n")
    message_id, ts = db.write_message(_connect(), session_id, body)
    click.echo(json.dumps({"id": message_id, "ts": ts, "session": session_id}))


@main.command()
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, help="emit a JSON array (machine-readable) instead of a table")
def read(session_id: str, as_json: bool) -> None:
    """Print messages since SESSION_ID's own last message."""
    rows = db.read_since_last(_connect(), session_id)
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        _console.print("[dim]no new messages[/dim]")
        return
    table = Table(title=f"messages since {session_id}'s last", show_lines=True)
    table.add_column("id", justify="right", style="cyan", no_wrap=True)
    table.add_column("ts", style="green", no_wrap=True)
    table.add_column("session", style="magenta")
    table.add_column("msg")
    for r in rows:
        table.add_row(str(r["id"]), r["ts"], r["session_id"], r["msg"])
    _console.print(table)
