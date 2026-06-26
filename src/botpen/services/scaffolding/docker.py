"""Docker provisioning for scaffolded agents: shared volume, build+run, attach, and ACLs.

This module runs INSIDE the Hub container, which mounts the shared volume at /shared and carries the
acl tools - so volume/ACL maintenance runs directly (no throwaway helper container). Agent
containers are built and run through the mounted docker socket (docker-out-of-docker).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import arrow

# pyrefly: ignore [missing-import]
from config import settings


def ensure_shared_volume() -> None:
    """Create the shared volume if absent (idempotent)."""
    subprocess.run(["docker", "volume", "create", settings.SHARED_VOLUME_NAME], check=True, capture_output=True)


def ensure_agent_dir(scaffold_id: str, uid: int, gid: int) -> None:
    """Create /shared/<scaffold_id>/workspace on the shared volume, owned by uid:gid and
    mode 0700 so other uids cannot enter or read the folder."""
    _helper(
        f"mkdir -p /shared/{scaffold_id}/workspace"
        f" && chown -R {uid}:{gid} /shared/{scaffold_id}"
        f" && chmod 700 /shared/{scaffold_id}"
    )


def build_and_up(playground: Path) -> None:
    """`docker compose build` + `up -d` for a playground (blocking)."""
    compose = str(playground / "docker-compose.yml")
    subprocess.run(["docker", "compose", "-f", compose, "up", "-d", "--build"], check=True)


def attach(container_name: str) -> None:
    """Drop the operator into the container's shell (interactive)."""
    subprocess.run(["docker", "exec", "-it", container_name, "bash"])


def _helper(script: str) -> None:
    """Run a shared-volume maintenance command directly. The Hub container mounts the shared volume
    at /shared and ships the acl tools, so no throwaway helper container is needed."""
    subprocess.run(["sh", "-c", script], check=True, capture_output=True, text=True)


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


def reap_stopped(after_mins: int) -> list[str]:
    """Teardown: reap every agent whose container has been exited longer than `after_mins` -
    remove the container, its image, its shared user folder, and its playground folder.
    Returns the reaped slugs. Best-effort: a docker/parse error on one agent skips it, not the rest."""
    listed = subprocess.run(
        ["docker", "ps", "-a", "--filter", "status=exited", "--filter", "name=botpen-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    ).stdout.split()
    cutoff = arrow.utcnow().shift(minutes=-after_mins)
    playgrounds = settings.WORKING_DIR / "playgrounds"
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
        for p in playgrounds.glob(f"*.{slug}"):
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


def teardown(components: list[str]) -> dict:
    """Remove the selected Docker artifacts for botpen. `components` is a subset of
    {``containers``, ``images``, ``volumes``}:
    - ``containers``: ``docker rm -f`` every ``botpen-`` container.
    - ``images``: ``docker rmi -f`` every ``botpen-*`` image (agents + the Hub).
    - ``volumes``: remove every ``botpen`` volume (shared + any stale per-agent workspace volumes).

    Also removes every ``botpen`` network when containers are torn down. Playground folders and the
    DB are handled by the caller (the `clean` command). Returns removal counts.
    """
    removed_containers: list[str] = []
    removed_images: list[str] = []
    removed_volumes: list[str] = []
    removed_networks: list[str] = []

    if "containers" in components:
        names = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=botpen-", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        ).stdout.split()
        for name in names:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        removed_containers = names

    if "images" in components:
        # botpen-* catches the agent images (botpen-agent-<slug>) and the Hub image (botpen-hub).
        imgs = set(
            subprocess.run(
                ["docker", "images", "--filter", "reference=botpen-*", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                text=True,
            ).stdout.split()
        )
        for image in imgs:
            subprocess.run(["docker", "rmi", "-f", image], capture_output=True)
        removed_images = list(imgs)

    if "volumes" in components:
        # Every botpen volume - the shared volume + any stale per-agent workspace volumes.
        vols = subprocess.run(
            ["docker", "volume", "ls", "-q", "--filter", "name=botpen"], capture_output=True, text=True
        ).stdout.split()
        for v in vols:
            subprocess.run(["docker", "volume", "rm", "-f", v], capture_output=True)
            removed_volumes.append(v)

    if "containers" in components:
        # Every botpen network (the shared `botpen` net + any per-project `_default` leftovers);
        # only removable once the containers above are gone.
        nets = subprocess.run(
            ["docker", "network", "ls", "-q", "--filter", "name=botpen"], capture_output=True, text=True
        ).stdout.split()
        for n in nets:
            if subprocess.run(["docker", "network", "rm", n], capture_output=True).returncode == 0:
                removed_networks.append(n)

    return {
        "containers": len(removed_containers),
        "images": len(removed_images),
        "volumes": len(removed_volumes),
        "networks": len(removed_networks),
    }
