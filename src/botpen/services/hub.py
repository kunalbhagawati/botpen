"""Host-side Hub lifecycle: bring the Hub CONTAINER up on demand, idempotently.

The Hub runs as a compose service (docker-compose.hub.yml, image botpen-hub) on the shared `botpen`
bridge network. It owns the DB (botpen-db volume), spawns agent containers via the mounted docker
socket, and mounts the shared volume to apply ACLs directly. Every agent joins the same `botpen`
network and reaches the Hub by name (hub:8787 / hub:8788).

Idempotent: a call while the Hub container is already running is a no-op - scaffold runs repeatedly,
so it must never start a second daemon.
"""

from __future__ import annotations

import os
import subprocess
import sys

# pyrefly: ignore [missing-import]
from config import settings

NETWORK = "botpen"
HUB_CONTAINER = "botpen-hub"
_HUB_COMPOSE = "docker-compose.hub.yml"
# Absolute venv python inside the Hub image (`python` on PATH is the system interpreter, no deps).
HUB_PYTHON = "/app/.venv/bin/python"


def running_in_hub() -> bool:
    """True when this process is executing INSIDE the Hub container (set by the image)."""
    return bool(os.environ.get("BOTPEN_IN_HUB"))


def hub_is_up() -> bool:
    """True if the Hub container is currently running."""
    out = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{HUB_CONTAINER}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    ).stdout
    return HUB_CONTAINER in out.split()


def ensure_network() -> None:
    """Create the shared `botpen` bridge network if absent (idempotent). The Hub and every agent
    join it, so they resolve each other by name."""
    subprocess.run(["docker", "network", "create", NETWORK], capture_output=True)


def ensure_hub() -> bool:
    """Bring up the Hub container if it is not already running. Idempotent (no-op when up). Builds
    the image on first run. Returns True if it started the Hub."""
    if hub_is_up():
        return False
    ensure_network()
    subprocess.run(["docker", "volume", "create", settings.SHARED_VOLUME_NAME], capture_output=True)
    subprocess.run(
        ["docker", "compose", "-f", str(settings.WORKING_DIR / _HUB_COMPOSE), "up", "-d", "--build"],
        cwd=settings.WORKING_DIR,
        check=True,
    )
    return True


def exec_in_hub(container_argv: list[str]) -> None:
    """Ensure the Hub is up, then REPLACE this host process with `docker exec` running the given
    command inside the Hub container (where the DB + docker socket live). Used by the host CLI shims
    for DB-touching commands (scaffold / db / permissions / playground)."""
    ensure_hub()
    tty_flag = "-it" if sys.stdin.isatty() else "-i"
    os.execvp("docker", ["docker", "exec", tty_flag, HUB_CONTAINER, *container_argv])
