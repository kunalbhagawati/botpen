"""The `hub` command - runs INSIDE the Hub container, never on the host.

`hub serve` is the long-lived daemon agents talk to (Thrift + WebSocket); `hub permissions` /
`hub workspace` / `hub reap` do one-shot `/shared` maintenance. Host code never imports this
package - it invokes the `hub` binary in a throwaway container. See ARCHITECTURE.md
"Three commands, three contexts".
"""

from __future__ import annotations

from .cli import entrypoint

__all__ = ["entrypoint"]
