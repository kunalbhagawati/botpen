"""Host-side Docker provisioning for scaffolded agents: shared volume, build+run, attach, teardown.

This module runs on the HOST. Agent containers are built and run through the host Docker daemon.
Work that must happen *inside* the shared volume (`/shared` mkdir/chown, ACLs, reap) cannot be done
from the host - the named volume lives inside the Docker VM - so it is delegated to the `hub` command
in a throwaway Hub container (`ensure_agent_dir` below) or done in-process by the running daemon
(`botpen.hub.shared`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import settings

from .. import hub as hub_service


def ensure_shared_volume() -> None:
    """Create the shared volume if absent (idempotent)."""
    subprocess.run(["docker", "volume", "create", settings.SHARED_VOLUME_NAME], check=True, capture_output=True)


def ensure_agent_dir(scaffold_id: str, uid: int, gid: int) -> None:
    """Create /shared/<scaffold_id>/workspace owned by uid:gid (mode 0700).

    The shared volume lives inside the Docker VM, so the host can't mkdir/chown on it directly; a
    throwaway Hub container with the volume mounted does it via `hub workspace create`."""
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{settings.SHARED_VOLUME_NAME}:/shared",
            hub_service.HUB_IMAGE,
            "workspace",
            "create",
            scaffold_id,
            str(uid),
            str(gid),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def build_and_up(playground: Path) -> None:
    """`docker compose build` + `up -d` for a playground (blocking)."""
    compose = str(playground / "docker-compose.yml")
    subprocess.run(["docker", "compose", "-f", compose, "up", "-d", "--build"], check=True)


def attach(container_name: str) -> None:
    """Drop the operator into the container's shell (interactive)."""
    subprocess.run(["docker", "exec", "-it", container_name, "bash"])


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
