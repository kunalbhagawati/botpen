"""``serve`` command (host): bring the Hub container up.

The Hub daemon itself runs *inside* the container as `hub serve` (see :mod:`botpen.hub`); this
host-side command just brings that container up via compose. Idempotent - a no-op when already up.
"""

from __future__ import annotations

import click

from ..services import hub as hub_service


@click.command()
def serve() -> None:
    """Bring the Hub container up (idempotent). The daemon runs as `hub serve` inside it."""
    started = hub_service.ensure_hub()
    click.echo("Hub container started." if started else "Hub already running.")
    click.echo("  logs: docker logs -f botpen-hub")
