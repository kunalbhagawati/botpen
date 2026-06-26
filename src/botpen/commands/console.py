# Shared rich console + boxed-output helper for human-facing CLI output.
from __future__ import annotations

from rich.console import Console, RenderableType
from rich.panel import Panel

console = Console()


def box(content: RenderableType, title: str | None = None, style: str = "blue") -> None:
    """Print `content` inside a rich panel (box) - the standard look for user-side command output."""
    console.print(Panel(content, title=title, border_style=style, padding=(0, 1)))
