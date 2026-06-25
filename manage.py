#!/usr/bin/env -S uv run --quiet python
"""Repo-root entry point for botpen (Django-style).

The shebang runs the file through uv, so `./manage.py ...` uses the project venv. Running a script
*by path* also puts the repo root on ``sys.path`` so the root-level ``config`` module is importable.

Dispatch model (the Hub is a container; the DB lives on a volume the macOS host can't reach):
- INSIDE the Hub container (BOTPEN_IN_HUB set): run the click command directly.
- On the host: `serve` brings the Hub container up; `teardown` and help run host-side (they manage
  the Hub's lifecycle); every other command (scaffold / db / permissions) is re-run INSIDE the Hub
  container via `docker exec`, where the DB + docker socket live.

Run (either form):
    ./manage.py serve                      # bring the Hub container up
    ./manage.py scaffold --language python # runs inside the Hub
    ./manage.py teardown --db
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _run_local() -> None:
    """Run the click group in this process (in-Hub, or host-side lifecycle commands)."""
    # pyrefly: ignore [missing-import]
    from config import settings  # noqa: F401  -- build the settings singleton up front

    from botpen.cli import cli

    cli()


def main() -> None:
    from botpen.services.hub import HUB_PYTHON, ensure_hub, exec_in_hub, running_in_hub

    # Inside the Hub container: the click command runs directly (serve = the actual daemon).
    if running_in_hub():
        _run_local()
        return

    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""

    # Help / no command renders in this process. (Cleanup moved to `playground clean`.)
    if not cmd or cmd.startswith("-"):
        _run_local()
        return

    # serve = bring the Hub container up (the daemon itself runs inside it).
    if cmd == "serve":
        started = ensure_hub()
        print("Hub container started." if started else "Hub already running.")
        print("  logs: docker logs -f botpen-hub")
        return

    # Everything else needs the DB + docker socket -> run it inside the Hub container.
    exec_in_hub([HUB_PYTHON, "manage.py", *argv])


if __name__ == "__main__":
    main()
