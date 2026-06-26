"""Presentation helpers for human-facing CLI output.

Owns the shared Rich console instance, the standard boxed-panel helper, and
any command-specific rendering that belongs to the presentation layer rather
than business logic.
"""

from __future__ import annotations

import json

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table

console = Console()


def box(content: RenderableType, title: str | None = None, style: str = "blue") -> None:
    """Print `content` inside a rich panel (box) - the standard look for user-side command output."""
    console.print(Panel(content, title=title, border_style=style, padding=(0, 1)))


def render_body(body) -> str:
    """Render a message body for display: plain strings pass through; dicts/lists are JSON-formatted."""
    return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)


def print_plan(agent_configs: list[tuple[int, str, list[str], str]], mapping_rule: str) -> None:
    """Print the resolved agent plan as a boxed rich table."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Model", style="bold")
    table.add_column("Stack items")

    for idx, model, stack_items, _ in agent_configs:
        table.add_row(
            str(idx),
            model,
            ", ".join(stack_items) if stack_items else "[dim](none)[/dim]",
        )

    panel = Panel(
        table,
        title=f"[bold]Playground plan[/bold]  ({mapping_rule})",
        border_style="blue",
        padding=(0, 1),
    )
    console.print(panel)
