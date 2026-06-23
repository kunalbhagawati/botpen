"""click command groups, one module per CLI: ``messages``, ``db``, ``permissions``.

Each module defines its group, attaches its commands, and is exposed directly as a console
script via ``[project.scripts]`` (e.g. ``bots.commands.messages:messages``).
"""
