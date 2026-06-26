"""The `hub` Click group - the command surface that exists only INSIDE the Hub container.

`hub serve` is the long-lived daemon; `hub permissions` / `hub workspace` / `hub reap` do one-shot
`/shared` maintenance. The host fires the one-shot ops in a throwaway `docker run --rm` container,
so this module keeps its top-level imports **config-free** (no `.env` is mounted into a throwaway):
`config.settings` and the daemon are imported lazily, only by the commands that need them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root = four levels up (src/botpen/hub/cli.py); on sys.path so the lazy `from config import
# settings` in serve/reap resolves when `hub` runs as an installed console script.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import click

from . import shared as shared_ops


@click.group()
def hub() -> None:
    """botpen Hub container ops: serve the daemon, maintain /shared (permissions / workspace / reap)."""


@hub.command("serve")
def serve_cmd() -> None:
    """Run the Hub daemon (Thrift RPC + WebSocket push). Foreground, Ctrl-C to stop."""
    from .daemon import run_serve  # lazy: keep non-serve hub ops free of the settings load

    run_serve()


@hub.group("permissions")
def permissions() -> None:
    """Apply / revoke POSIX ACLs for a peer under an owner's /shared workspace."""


@permissions.command("grant")
@click.argument("owner_scaffold_id")
@click.argument("peer_uid", type=int)
@click.argument("grant_json")
def permissions_grant(owner_scaffold_id: str, peer_uid: int, grant_json: str) -> None:
    """Grant PEER_UID the ACLs described by GRANT_JSON (a grant tree) under OWNER's workspace."""
    shared_ops.apply_acl(owner_scaffold_id, peer_uid, json.loads(grant_json))
    click.echo(json.dumps({"ok": True, "op": "grant", "owner": owner_scaffold_id, "peer_uid": peer_uid}))


@permissions.command("revoke")
@click.argument("owner_scaffold_id")
@click.argument("peer_uid", type=int)
@click.argument("grant_json")
def permissions_revoke(owner_scaffold_id: str, peer_uid: int, grant_json: str) -> None:
    """Revoke PEER_UID's ACLs for the paths in GRANT_JSON under OWNER's workspace."""
    shared_ops.revoke_acl(owner_scaffold_id, peer_uid, json.loads(grant_json))
    click.echo(json.dumps({"ok": True, "op": "revoke", "owner": owner_scaffold_id, "peer_uid": peer_uid}))


@hub.group("workspace")
def workspace() -> None:
    """Manage an agent's /shared workspace directory."""


@workspace.command("create")
@click.argument("scaffold_id")
@click.argument("uid", type=int)
@click.argument("gid", type=int)
def workspace_create(scaffold_id: str, uid: int, gid: int) -> None:
    """Create /shared/SCAFFOLD_ID/workspace owned by UID:GID, mode 0700."""
    shared_ops.create_workspace(scaffold_id, uid, gid)
    click.echo(json.dumps({"ok": True, "scaffold": scaffold_id, "uid": uid, "gid": gid}))


@hub.command("reap")
@click.option("--after-mins", "after_mins", type=int, default=None, help="override SCAFFOLD_TEARDOWN_AFTER_MINS")
def reap_cmd(after_mins: int | None) -> None:
    """Reap agents whose container has been stopped longer than the teardown window."""
    from config import settings  # lazy: keep non-reap hub ops config-free (no settings load)

    mins = after_mins if after_mins is not None else settings.SCAFFOLD_TEARDOWN_AFTER_MINS
    reaped = shared_ops.reap_stopped(mins, settings.WORKING_DIR / "playgrounds")
    click.echo(json.dumps({"event": "reaped", "slugs": reaped}))


def hub_main() -> None:
    hub()


if __name__ == "__main__":
    hub_main()
