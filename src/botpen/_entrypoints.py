"""Console-script entry points for botpen.

Each entry point must inject the repo root onto sys.path before any
root-level module (``config``) is imported. This mirrors the same trick
manage.py uses so that ``from config import settings`` works when the
command is invoked as an installed script (not via ./manage.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root = two levels up from this file (src/botpen/_entrypoints.py)
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def playground_main() -> None:
    # Import deferred until after path injection above
    from botpen.commands.playground import playground  # noqa: PLC0415

    playground()
