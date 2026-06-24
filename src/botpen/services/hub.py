"""Host-side Hub process management: bring the daemon up on demand, idempotently.

`scaffold` (with an auto-started bot) assumes the Hub is reachable, so it spins one up unless told
not to. Because scaffold runs repeatedly, this must be idempotent - a call while a Hub is already
listening is a no-op, never a second (port-colliding) daemon.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time

# pyrefly: ignore [missing-import]
from config import settings


def hub_is_up() -> bool:
    """True if something is already listening on the Hub's Thrift port (127.0.0.1:DAEMON_PORT)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", settings.DAEMON_PORT)) == 0


def ensure_hub() -> bool:
    """Start the Hub daemon in the background if it is not already up. Idempotent (a call while the
    Hub is listening is a no-op). The daemon is detached (`start_new_session`) so it outlives the
    scaffold process; its output goes to `.hub.log`. Returns True if a new Hub was spawned.

    Raises if a freshly-spawned Hub does not bind within the timeout."""
    if hub_is_up():
        return False
    log = settings.WORKING_DIR / ".hub.log"
    subprocess.Popen(
        [sys.executable, str(settings.WORKING_DIR / "manage.py"), "serve"],
        stdout=log.open("a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(100):  # up to ~10s for migrations + bind
        if hub_is_up():
            return True
        time.sleep(0.1)
    raise RuntimeError(f"Hub did not come up within 10s - see {log}")
