"""SQLite-backed mailbox for coordinating agents.

The CLI is rooted at the repo-level ``manage.py``; this package holds the Click groups
(``commands/``) and the data layer (``core/`` engine+models, ``services/`` operations).
App config lives at the repo root (``config.py``).
"""
