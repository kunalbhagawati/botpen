"""SQLite-backed mailbox for coordinating agents.

The host CLI is the ``botpen`` command (``_entrypoints:botpen_main`` / the repo-root ``botpen``
shebang); this package holds the Click groups (``commands/``), the in-Hub-container ``hub`` command
(``hub/``), and the data layer (``core/`` engine+models, ``services/`` operations).
App config lives at the repo root (``config.py``).
"""
