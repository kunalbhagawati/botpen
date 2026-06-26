"""Console-script entry point for the host `botpen` command.

It injects the repo root onto sys.path before any root-level module (``config``) is imported - the
path has to be set first, the same trick the repo-root ``botpen`` shebang uses - so that
``from config import settings`` works when invoked as the installed console script (not via
``./botpen``). Imports below that bootstrap are intentionally not at the top of the file (ruff E402
is ignored for this module in pyproject).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root = three levels up from this file (src/botpen/_entrypoints.py). Must be on sys.path
# BEFORE the imports below, so `config` (a repo-root module, not part of the package) resolves.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import settings  # noqa: F401 - build the settings singleton up front

from botpen.cli import cli


def botpen_main() -> None:
    cli()
