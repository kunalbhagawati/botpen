"""Host-side Hub lifecycle: bring the Hub CONTAINER up on demand, idempotently.

The Hub runs as a compose service (docker-compose.hub.yml, image botpen-hub) on the shared `botpen`
bridge network. Inside it runs `hub serve` - the single DB writer + agent endpoint; it also mounts
the shared volume so its in-process `/shared` ACL/reap maintenance works directly. Every agent joins
the same `botpen` network and reaches the Hub by name (hub:8787 / hub:8788).

Idempotent: a call while the Hub container is already running is a no-op - scaffold runs repeatedly,
so it must never start a second daemon.
"""

from __future__ import annotations

import subprocess

from config import settings

NETWORK = "botpen"
HUB_CONTAINER = "botpen-hub"
HUB_IMAGE = "botpen-hub"
_HUB_COMPOSE = "docker-compose.hub.yml"


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
    # Host dir for the DB bind mount (./.db -> /data in the Hub), so file-based explorers can open it.
    (settings.WORKING_DIR / ".db").mkdir(exist_ok=True)
    subprocess.run(
        ["docker", "compose", "-f", str(settings.WORKING_DIR / _HUB_COMPOSE), "up", "-d", "--build"],
        cwd=settings.WORKING_DIR,
        check=True,
    )
    return True
