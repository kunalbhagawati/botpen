"""Render the playground skeleton from the Copier template, and stage the binary build inputs.

The Dockerfile builds the `coordinate` binary from a build context that is the playground directory
itself, so the agent never sees the repo. We therefore copy the binary's sources into
`playgrounds/<slug>/.coordinate-src/` at scaffold time.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from copier import run_copy

# pyrefly: ignore [missing-import]
from config import settings

from ...stack_catalog import SCAFFOLD_STACK_CATALOG

_TEMPLATE_ROOT = settings.WORKING_DIR / "src" / "resources" / "skeleton"
_COORDINATE_SRC = settings.WORKING_DIR / "src" / "coordinate_cli"
_IDL = settings.WORKING_DIR / "src" / "resources" / "hub.thrift"

_ENTRY = "from coordinate_cli.cli import cli\n\nif __name__ == '__main__':\n    cli()\n"


def stack_packages(stack: dict[str, list[str]] | None) -> list[str]:
    """Resolve the selected stack (category -> chosen keys) to the deduped union of apk packages."""
    pkgs: list[str] = []
    for category, selected in (stack or {}).items():
        by_key = {e["key"]: e["packages"] for e in SCAFFOLD_STACK_CATALOG.get(category, [])}
        for key in selected or []:
            for pkg in by_key.get(key, []):
                if pkg not in pkgs:
                    pkgs.append(pkg)
    return pkgs


def render(dest: Path, data: dict[str, Any]) -> None:
    """Render the Copier template into `dest` (non-interactive)."""
    run_copy(str(_TEMPLATE_ROOT), str(dest), data=data, defaults=True, unsafe=True, quiet=True)


def stage_build_inputs(dest: Path, secret_key: str) -> None:
    """Copy the `coordinate` binary sources into `<dest>/.coordinate-src/` for the Dockerfile build,
    baking this scaffold's secret token into `_identity.py` so it travels inside the compiled binary
    (never in an env var, never handled by the agent)."""
    src = dest / ".coordinate-src"
    (src / "coordinate_cli").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        _COORDINATE_SRC, src / "coordinate_cli", dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (src / "coordinate_cli" / "_identity.py").write_text(f'TOKEN = "{secret_key}"\n')
    shutil.copy2(_IDL, src / "hub.thrift")
    (src / "entry.py").write_text(_ENTRY)
