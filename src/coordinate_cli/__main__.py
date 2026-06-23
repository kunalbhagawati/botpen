"""Entry point: `python -m coordinate_cli ...` (and the PyInstaller binary `coordinate`)."""

from __future__ import annotations

from .cli import cli

if __name__ == "__main__":
    cli()
