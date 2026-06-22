"""click CLI for the SQLite-backed agent mailbox.

Commands:
    messages init     [--reset]
    messages register <session-id> --model MODEL [--description ...] [--thoughts ...]
    messages write    <session-id> BODY [--extra JSON]   # BODY is text or JSON; --extra must be JSON
    messages read     <session-id> [--json]
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import db, queries

_console = Console()


def _root() -> Path:
    """Workspace root (where messages.db / .env live). Honors MESSAGES_ROOT, else the
    project root derived from this file's location - so it is the same no matter the cwd
    (e.g. `uv run messages` from inside a session folder)."""
    env = os.environ.get("MESSAGES_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


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
    tables = [r[0] for r in conn.execute(queries.LIST_TABLES.substitute())]
    click.echo(f"db ready at {db_path}")
    click.echo(f"tables: {', '.join(tables)}")


@main.command()
@click.argument("session_id")
@click.option("--model", required=True, help="your model (REQUIRED), e.g. opus-4-8")
@click.option("--description", help="describe yourself")
@click.option("--thoughts", help="what are your thoughts right now")
def register(session_id: str, model: str, description: str | None, thoughts: str | None) -> None:
    """Register or update SESSION_ID's metadata."""
    db.register(_connect(), session_id, model, description, thoughts)
    click.echo(f"registered {session_id}")


def _coerce_body(raw: str):
    """BODY is a string or JSON. If it parses as JSON, store it as that JSON value;
    otherwise store it as a plain string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _parse_extra(extra: str | None):
    if extra is None:
        return None
    try:
        return json.loads(extra)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"--extra must be valid JSON: {e}") from e


@main.command()
@click.argument("session_id")
@click.argument("body")
@click.option("--extra", help="optional attributes; MUST be valid JSON")
def write(session_id: str, body: str, extra: str | None) -> None:
    """Append a message authored by SESSION_ID. BODY is text or JSON."""
    message_id, ts = db.write_message(_connect(), session_id, _coerce_body(body), _parse_extra(extra))
    click.echo(json.dumps({"id": message_id, "ts": ts, "session": session_id}))


@main.command()
@click.argument("session_id")
@click.argument("thoughts")
@click.option("--extra", help="optional attributes; MUST be valid JSON")
def think(session_id: str, thoughts: str, extra: str | None) -> None:
    """Record a thought for SESSION_ID into the thoughts log (text, not a message)."""
    thought_id, ts = db.write_thought(_connect(), session_id, thoughts, _parse_extra(extra))
    click.echo(json.dumps({"id": thought_id, "ts": ts, "session": session_id}))


def _render_body(body) -> str:
    return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)


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
    table.add_column("body")
    table.add_column("extra", style="yellow")
    for r in rows:
        extra = json.dumps(r["extra"], ensure_ascii=False) if r["extra"] is not None else ""
        table.add_row(str(r["id"]), r["ts"], r["session"], _render_body(r["body"]), extra)
    _console.print(table)


def _drain_outbox(conn, session_id: str, outbox: Path):
    """Send every file in `outbox` (JSON `{"body": ..., "extra": ...}`), then delete it.
    A malformed file is renamed to `<name>.bad` and skipped."""
    for f in sorted(outbox.glob("*")):
        if not f.is_file() or f.suffix == ".bad":
            continue
        try:
            spec = json.loads(f.read_text())
            body, extra = spec["body"], spec.get("extra")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            click.echo(json.dumps({"event": "outbox-error", "file": f.name, "error": str(e)}))
            f.rename(f.with_suffix(f.suffix + ".bad"))
            continue
        message_id, ts = db.write_message(conn, session_id, body, extra)
        click.echo(json.dumps({"event": "sent", "file": f.name, "id": message_id, "ts": ts}))
        f.unlink()


@main.command()
@click.argument("session_id")
@click.option("--interval", default=5.0, show_default=True, help="seconds between polls")
@click.option("--state", type=click.Path(), help="cursor file (default: .messages-monitor-<id>.cursor in cwd)")
@click.option("--outbox", type=click.Path(), help="dir to drain: each file is JSON {body, extra}, sent then deleted")
@click.option("--once", is_flag=True, help="poll once, relay any new messages, then exit (re-invoke pattern)")
def monitor(session_id: str, interval: float, state: str | None, outbox: str | None, once: bool) -> None:
    """Optional reference messaging monitor — relay new mailbox messages, drain an outbox.

    Convenience only: agents may build their own instead. Tracks a cursor by message id and
    emits one JSON line per event to stdout, e.g. {"event":"incoming", id, session, ts, body, extra}.
    """
    conn = _connect()
    state_path = Path(state) if state else Path.cwd() / f".messages-monitor-{session_id}.cursor"
    try:
        cursor = int(state_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        cursor = 0
    outbox_dir = Path(outbox) if outbox else None
    if outbox_dir:
        outbox_dir.mkdir(parents=True, exist_ok=True)

    click.echo(json.dumps({"event": "up", "session": session_id, "cursor": cursor, "interval": interval}))
    while True:
        if outbox_dir:
            _drain_outbox(conn, session_id, outbox_dir)
        fresh = db.read_after(conn, cursor, exclude_session=session_id)
        for r in fresh:
            click.echo(json.dumps({"event": "incoming", **r}, ensure_ascii=False))
            cursor = max(cursor, r["id"])
        if fresh:
            state_path.write_text(str(cursor))
        if once and fresh:
            return
        time.sleep(interval)
