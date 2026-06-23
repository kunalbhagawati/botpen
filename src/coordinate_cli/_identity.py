"""Baked-in agent identity.

`scaffold new` overwrites this module in the build inputs with the scaffold's real secret before
PyInstaller bundles the binary, so the token travels inside the compiled `coordinate` binary - never
in an env var, never passed by the agent. This repo copy is an empty placeholder; in dev the client
falls back to the COORDINATE__TOKEN env var.
"""

from __future__ import annotations

TOKEN = ""
