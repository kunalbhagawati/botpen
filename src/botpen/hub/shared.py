"""Shared-volume maintenance, run INSIDE the Hub container.

The Hub container mounts the shared volume at `/shared` and ships the `acl` tools, so these run
directly (`sh -c`), no throwaway helper container. Two callers reach them:

- the **daemon** (`hub serve`) calls `apply_acl` / `revoke_acl` / `reap_stopped` in-process at runtime;
- the **host** (`botpen scaffold`) fires a throwaway `docker run --rm <hub-image> hub workspace …`
  for one-shot `/shared` work it cannot do itself.

This module is deliberately **config-free** - it takes everything it needs as arguments - so a
throwaway `hub workspace` / `hub permissions` run needs no `.env` mounted into the container.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import arrow


def _helper(script: str) -> None:
    """Run a shared-volume maintenance command directly. The Hub container mounts the shared volume
    at /shared and ships the acl tools, so no throwaway helper container is needed."""
    subprocess.run(["sh", "-c", script], check=True, capture_output=True, text=True)


def create_workspace(scaffold_id: str, uid: int, gid: int) -> None:
    """Create /shared/<scaffold_id>/workspace on the shared volume, owned by uid:gid and
    mode 0700 so other uids cannot enter or read the folder."""
    _helper(
        f"mkdir -p /shared/{scaffold_id}/workspace"
        f" && chown -R {uid}:{gid} /shared/{scaffold_id}"
        f" && chmod 700 /shared/{scaffold_id}"
    )


def _walk(node: dict, owner_scaffold_id: str, peer_uid: int, base: str = "") -> list[str]:
    """Flatten a grant tree into setfacl argument fragments `[-R ]u:<uid>:<perms> <abs path>`."""
    rel = f"{base}/{node['path']}".strip("/")
    target = f"/shared/{owner_scaffold_id}/workspace/{rel}"
    flag = "-R " if node.get("is_recursive") else ""
    frags = [f'{flag}-m u:{peer_uid}:{node.get("permissions", "rx")} "{target}"']
    for child in node.get("children", []) or []:
        frags.extend(_walk(child, owner_scaffold_id, peer_uid, rel))
    return frags


def apply_acl(owner_scaffold_id: str, peer_uid: int, grant: Any) -> None:
    """Apply a grant tree's ACLs for `peer_uid` under the owner's /shared/<scaffold_id>/workspace/.

    Before per-node grants, grants traverse (x) on the two parent dirs so the peer can reach
    granted paths without being able to ls those folders.
    """
    # Traverse-only access on the parent dirs - x only, not r, so ls is still blocked.
    _helper(f"setfacl -m u:{peer_uid}:x /shared/{owner_scaffold_id}")
    _helper(f"setfacl -m u:{peer_uid}:x /shared/{owner_scaffold_id}/workspace")
    nodes = grant if isinstance(grant, list) else [grant]
    for node in nodes:
        for frag in _walk(node, owner_scaffold_id, peer_uid):
            _helper(f"setfacl {frag}")


def revoke_acl(owner_scaffold_id: str, peer_uid: int, grant: Any) -> None:
    """Remove `peer_uid`'s ACL entries for the grant tree's paths."""
    nodes = grant if isinstance(grant, list) else [grant]
    for node in nodes:
        rel = node["path"].strip("/")
        flag = "-R " if node.get("is_recursive") else ""
        _helper(f'setfacl {flag}-x u:{peer_uid} "/shared/{owner_scaffold_id}/workspace/{rel}"')


def reap_stopped(after_mins: int, playgrounds_dir: Path) -> list[str]:
    """Teardown: reap every agent whose container has been exited longer than `after_mins` -
    remove the container, its image, its shared user folder, and its playground folder.
    Returns the reaped slugs. Best-effort: a docker/parse error on one agent skips it, not the rest."""
    listed = subprocess.run(
        ["docker", "ps", "-a", "--filter", "status=exited", "--filter", "name=botpen-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    ).stdout.split()
    cutoff = arrow.utcnow().shift(minutes=-after_mins)
    reaped: list[str] = []
    for name in listed:
        slug = name.removeprefix("botpen-")
        finished = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.FinishedAt}}", name],
            capture_output=True,
            text=True,
        ).stdout.strip()
        try:
            if arrow.get(finished) > cutoff:  # stopped too recently - leave it
                continue
        except Exception:
            continue
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "rmi", "-f", f"botpen-agent-{slug}"], capture_output=True)
        # Resolve scaffold_id from playground folder name: {epoch}.{scaffold_id}.{slug}
        for p in playgrounds_dir.glob(f"*.{slug}"):
            parts = p.name.split(".", 2)
            if len(parts) == 3:
                scaffold_id = parts[1]
                try:
                    _helper(f"rm -rf /shared/{scaffold_id}")
                except Exception:
                    pass
            shutil.rmtree(p, ignore_errors=True)
        reaped.append(slug)
    return reaped
