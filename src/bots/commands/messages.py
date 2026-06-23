"""``messages`` command group: register / write / think / read / monitor."""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
from rich.table import Table

# pyrefly: ignore [missing-import]
from config import settings

from ..services import messages as messages_service
from ..services import permissions as permissions_service
from ..services.utils import normalize_session
from . import utils
from .console import console


@click.group()
def messages() -> None:
    """Agent mailbox: register, send, read, and relay messages."""


@click.command()
@click.argument("session_id")
@click.option("--model", required=True, help="your model (REQUIRED), e.g. opus-4-8")
@click.option("--description", help="describe yourself")
@click.option("--thoughts", help="what are your thoughts right now")
@click.option("--path", help="your session folder path ({epoch_milli}.{session-id})")
def register(
    session_id: str, model: str, description: str | None, thoughts: str | None, path: str | None
) -> None:
    """Register or update SESSION_ID's metadata."""
    messages_service.register(session_id, model, description, thoughts, path)
    click.echo(f"registered {session_id}")


@click.command()
@click.argument("session_id")
@click.argument("body")
@click.option("--extra", help="optional attributes; MUST be valid JSON")
@click.option("--to", "to_", multiple=True, help="recipient session id; repeat for several; omit = everyone")
def write(session_id: str, body: str, extra: str | None, to_: tuple[str, ...]) -> None:
    """Append a message authored by SESSION_ID. BODY is text or JSON.

    With no --to the message is a broadcast (everyone). Pass --to one or more times to
    address specific sessions; only they (and you) will see it.
    """
    to = list(to_) or None
    message_id, ts = messages_service.write_message(session_id, utils.coerce_body(body), utils.parse_extra(extra), to)
    click.echo(json.dumps({"id": message_id, "ts": ts, "session": session_id, "to": to}))


@click.command()
@click.argument("session_id")
@click.argument("thoughts")
@click.option("--extra", help="optional attributes; MUST be valid JSON")
def think(session_id: str, thoughts: str, extra: str | None) -> None:
    """Record a thought for SESSION_ID into the thoughts log (text, not a message)."""
    thought_id, ts = messages_service.write_thought(session_id, thoughts, utils.parse_extra(extra))
    click.echo(json.dumps({"id": thought_id, "ts": ts, "session": session_id}))


@click.command()
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, help="emit a JSON array (machine-readable) instead of a table")
def read(session_id: str, as_json: bool) -> None:
    """Print messages since SESSION_ID's own last message."""
    rows = messages_service.read_since_last(session_id)
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[dim]no new messages[/dim]")
        return
    table = Table(title=f"messages since {session_id}'s last", show_lines=True)
    table.add_column("id", justify="right", style="cyan", no_wrap=True)
    table.add_column("ts", style="green", no_wrap=True)
    table.add_column("session", style="magenta")
    table.add_column("to", style="blue")
    table.add_column("body")
    table.add_column("extra", style="yellow")
    for r in rows:
        extra = json.dumps(r["extra"], ensure_ascii=False) if r["extra"] is not None else ""
        to = ", ".join(r["to"]) if r["to"] else "all"
        table.add_row(str(r["id"]), r["ts"], r["session"], to, utils.render_body(r["body"]), extra)
    console.print(table)


def _drain_outbox(session_id: str, outbox: Path):
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
        message_id, ts = messages_service.write_message(session_id, body, extra)
        click.echo(json.dumps({"event": "sent", "file": f.name, "id": message_id, "ts": ts}))
        f.unlink()


@click.command()
@click.argument("session_id")
@click.option("--interval", default=5.0, show_default=True, help="seconds between polls")
@click.option("--state", type=click.Path(), help="cursor file (default: .tmp/.messages-monitor-<id>.cursor)")
@click.option("--outbox", type=click.Path(), help="dir to drain: each file is JSON {body, extra}, sent then deleted")
@click.option("--once", is_flag=True, help="poll once, relay any new messages, then exit (re-invoke pattern)")
def monitor(session_id: str, interval: float, state: str | None, outbox: str | None, once: bool) -> None:
    """Optional reference messaging monitor - relay new mailbox messages, drain an outbox.

    Convenience only: agents may build their own instead. Tracks a cursor by message id and
    emits one JSON line per event to stdout, e.g. {"event":"incoming", id, session, ts, body, extra}.
    Cursor state lives under the workspace `.tmp/` dir unless --state overrides it.
    """
    session_id = normalize_session(session_id)
    if state:
        state_path = Path(state)
    else:
        settings.TMP_DIR.mkdir(parents=True, exist_ok=True)
        state_path = settings.TMP_DIR / f".messages-monitor-{session_id}.cursor"
    perm_state_path = Path(str(state_path) + ".perm")

    try:
        cursor = int(state_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        cursor = 0
    try:
        perm_cursor = perm_state_path.read_text().strip()  # ISO timestamp cursor
    except FileNotFoundError:
        perm_cursor = ""
    outbox_dir = Path(outbox) if outbox else None
    if outbox_dir:
        outbox_dir.mkdir(parents=True, exist_ok=True)

    click.echo(json.dumps({"event": "up", "session": session_id, "cursor": cursor, "perm_cursor": perm_cursor}))
    while True:
        if outbox_dir:
            _drain_outbox(session_id, outbox_dir)

        fresh = messages_service.read_after(cursor, exclude_session=session_id)
        for r in fresh:
            cursor = max(cursor, r["id"])
            if messages_service.visible_to(r, session_id):  # broadcast, or I'm a named recipient
                click.echo(json.dumps({"event": "incoming", **r}, ensure_ascii=False))
        if fresh:
            state_path.write_text(str(cursor))

        # Relay permission events both ways: requests to me as granter, decisions to me as asker.
        changed = permissions_service.permissions_changed(session_id, perm_cursor)
        for r in changed:
            if r["granter"] == session_id and r["status"] == "requested":
                click.echo(json.dumps({"event": "permission-request", **r}, ensure_ascii=False))
            elif r["asker"] == session_id and r["status"] in ("granted", "denied", "revoked"):
                click.echo(json.dumps({"event": "permission-decision", **r}, ensure_ascii=False))
            perm_cursor = max(perm_cursor, r["updated_at"])
        if changed:
            perm_state_path.write_text(perm_cursor)

        if once and (fresh or changed):
            return
        time.sleep(interval)


messages.add_command(register)
messages.add_command(write)
messages.add_command(think)
messages.add_command(read)
messages.add_command(monitor)
