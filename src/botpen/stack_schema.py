"""The agent's self-reported chosen-stack: a suggested (NOT enforced) JSON Schema and a concrete
example, returned together by the Hub's `stack_schema` RPC.

The example is kept OUT of the skill files on purpose: an example that sits in the agent's context
would bias its choices. The agent fetches it on demand, which also doubles as a check that it
follows instructions. We record whatever an agent sends, unvalidated - the value is in what the
incarnation expresses, not its structure.
"""

from __future__ import annotations

SCAFFOLD_STACK_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "agent chosen stack",
    "description": "Describe the stack you chose to run with. Free-form; recorded, never validated.",
    "type": "object",
    # additionalProperties: true on every object - each may carry extra arbitrary keys.
    "additionalProperties": True,
    "properties": {
        "languages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"},
                    "manager": {"type": "string"},
                },
            },
        },
        "databases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"name": {"type": "string"}, "version": {"type": "string"}},
            },
        },
        "tools": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": ["string", "array"], "items": {"type": "string"}},
    },
}


# The extra keys (frameworks / test_runner / typed / purpose / port / config) show that any object
# may carry arbitrary keys of any JSON type.
SCAFFOLD_STACK_EXAMPLE: dict = {
    "languages": [
        {
            "name": "python",
            "version": "3.14",
            "manager": "uv",
            "frameworks": ["fastapi", "sqlmodel"],
            "test_runner": "pytest",
            "typed": True,
        },
    ],
    "databases": [
        {"name": "redis", "version": "7", "purpose": "cache", "port": 6379, "config": {"maxmemory": "256mb"}},
    ],
    "tools": ["ffmpeg"],
    "notes": "small async API backed by a redis cache",
}
