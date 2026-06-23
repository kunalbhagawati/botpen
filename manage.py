#!/usr/bin/env -S uv run --quiet python
"""Repo-root entry point for botpen (Django-style).

The shebang runs the file through uv, so `./manage.py ...` uses the project venv (deps + the
right Python) - same as `uv run manage.py ...`. Running a script *by path* also puts its
directory (the repo root) on ``sys.path``, so the root-level ``config`` module is importable
everywhere downstream. This bootstraps that, builds the ``settings`` singleton, then runs the
root Click group with the command groups (db / permissions / serve / scaffold / teardown) mounted.

Run (either form):
    ./manage.py scaffold --language python
    uv run manage.py serve
    ./manage.py db setup
    ./manage.py teardown --db
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# pyrefly: ignore [missing-import]
from config import settings  # noqa: E402, F401  -- build the settings singleton up front

from botpen.cli import cli  # noqa: E402


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
