#!/usr/bin/env python3
"""Repo-root entry point for the bots mailbox (Django-style).

Running a script *by path* puts its directory (the repo root) on ``sys.path``, so the
root-level ``config`` module is importable everywhere downstream. This bootstraps that,
builds the ``settings`` singleton, then runs the root Click group with the three command
groups (``messages`` / ``db`` / ``permissions``) mounted as subcommands.

Run:
    uv run manage.py messages write <me> "hello"
    uv run manage.py db setup
    uv run manage.py permissions grant <me> <asker> --paths '["*.svg"]'
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# pyrefly: ignore [missing-import]
from config import settings  # noqa: E402, F401  -- build the settings singleton up front

from bots.cli import cli  # noqa: E402


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
