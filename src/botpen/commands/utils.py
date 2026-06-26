"""CLI input parsing / validation / stack resolution helpers.

Connection/path resolution lives in :mod:`botpen.core.db` and ``config.settings``; this module
is CLI input coercion, validation, and stack resolution.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import questionary

from ..stack_catalog import SCAFFOLD_STACK_CATALOG

# ---------------------------------------------------------------------------
# Model choices - single source of truth
# ---------------------------------------------------------------------------

MODEL_CHOICES: list[str] = ["opus", "sonnet", "haiku", "default"]


# ---------------------------------------------------------------------------
# Body / extra coercion (used by messages commands)
# ---------------------------------------------------------------------------


def coerce_body(raw: str):
    """BODY is a string or JSON. If it parses as JSON, store it as that JSON value;
    otherwise store it as a plain string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_extra(extra: str | None):
    if extra is None:
        return None
    try:
        return json.loads(extra)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"--extra must be valid JSON: {e}") from e


# ---------------------------------------------------------------------------
# Scaffold config parsing (internal helpers)
# ---------------------------------------------------------------------------


def _parse_stack_config(raw_stack) -> list[str]:
    """Normalize a ScaffoldStackConfig to a flat list of stack item name strings.

    Accepts:
      - ["python", "redis"]                            -> ["python", "redis"]
      - ["python", {"extra": "cfg"}]                   -> ["python"]  (2-elem [name, config])
      - [{"name": "python", "config": {...}}, ...]     -> ["python", ...]
    """
    names: list[str] = []
    if not isinstance(raw_stack, list):
        return names
    i = 0
    while i < len(raw_stack):
        item = raw_stack[i]
        if isinstance(item, str):
            # Could be a bare name or the first element of a [name, config] pair
            if i + 1 < len(raw_stack) and isinstance(raw_stack[i + 1], dict):
                # [name, config] pair - consume both
                names.append(item)
                # TODO: stack item extra config not yet wired
                i += 2
            else:
                names.append(item)
                i += 1
        elif isinstance(item, dict):
            # {"name": ..., "config": {...}}
            key = item.get("name") or item.get("key")
            if isinstance(key, str):
                names.append(key)
            # TODO: stack item extra config not yet wired
            i += 1
        else:
            i += 1
    return names


def _normalize_item(raw_item) -> tuple[str, list[str]]:
    """Normalize a ScaffoldItemConfig to (model, stack_items).

    Accepts:
      - "haiku"                                         -> ("haiku", [])
      - ["haiku", ["python", "redis"]]                  -> ("haiku", ["python", "redis"])
      - {"model": "haiku", "stack": ["python"]}         -> ("haiku", ["python"])
    """
    if isinstance(raw_item, str):
        return raw_item, []
    if isinstance(raw_item, list) and len(raw_item) >= 1 and isinstance(raw_item[0], str):
        model = raw_item[0]
        stack_raw = raw_item[1] if len(raw_item) >= 2 else []
        return model, _parse_stack_config(stack_raw)
    if isinstance(raw_item, dict):
        model = raw_item.get("model", "default")
        stack_raw = raw_item.get("stack", [])
        return str(model), _parse_stack_config(stack_raw if isinstance(stack_raw, list) else [])
    raise click.BadParameter(f"unrecognized scaffold config item: {raw_item!r}", param_hint="--scaffold-config")


# ---------------------------------------------------------------------------
# Scaffold config parsing (public)
# ---------------------------------------------------------------------------


def parse_scaffold_config(raw: str) -> list[tuple[str, list[str]]]:
    """Parse -c value into a list of (model, stack_items) tuples.

    Resolution order:
      1. If raw names an existing file, read its contents.
      2. Try json.loads. If it yields a list -> array-of-items form.
         If it yields a string, or raises -> treat as comma-separated model names.
    """
    source = raw
    p = Path(raw)
    if p.exists() and p.is_file():
        source = p.read_text()

    try:
        parsed = json.loads(source)
    except json.JSONDecodeError, ValueError:
        parsed = source  # treat as comma-separated string

    if isinstance(parsed, list):
        return [_normalize_item(item) for item in parsed]

    # String path: comma-separated model names
    tokens = str(parsed).split(",")
    return [_normalize_item(tok.strip()) for tok in tokens if tok.strip()]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_model(model: str) -> None:
    if model not in MODEL_CHOICES:
        raise click.BadParameter(
            f"model {model!r} is not one of {MODEL_CHOICES}",
            param_hint="--scaffold-config",
        )


def validate_and_group_stack(stack_items: list[str]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Map stack item names to (languages, dbs, tools) tuples, raising BadParameter for unknowns."""
    languages: list[str] = []
    dbs: list[str] = []
    tools: list[str] = []

    all_keys: dict[str, str] = {}  # key -> category
    for category, entries in SCAFFOLD_STACK_CATALOG.items():
        for entry in entries:
            all_keys[str(entry["key"])] = category

    for item in stack_items:
        cat = all_keys.get(item)
        if cat is None:
            valid = list(all_keys.keys())
            raise click.BadParameter(
                f"stack item {item!r} not found in catalog (valid: {valid})",
                param_hint="--scaffold-config",
            )
        if cat == "language":
            languages.append(item)
        elif cat == "db":
            dbs.append(item)
        elif cat == "tools":
            tools.append(item)

    return tuple(languages), tuple(dbs), tuple(tools)


# ---------------------------------------------------------------------------
# Stack resolution (interactive or from flags)
# ---------------------------------------------------------------------------


def resolve_stack(flags: dict[str, tuple[str, ...]], interactive: bool) -> dict[str, list[str]]:
    """Resolve each catalog category to a chosen SUBSET: explicit flags, an interactive
    multi-select, or empty (blank Alpine). Iterates the catalog, so new categories appear in the
    form without touching this code."""
    stack: dict[str, list[str]] = {}
    for category, entries in SCAFFOLD_STACK_CATALOG.items():
        keys = [e["key"] for e in entries]
        chosen = list(flags.get(category) or ())
        if not chosen and interactive:
            chosen = questionary.checkbox(f"{category}?", choices=keys).ask() or []
        for k in chosen:
            if k not in keys:
                raise click.BadParameter(f"{category}: '{k}' not in {keys}")
        stack[category] = chosen
    return stack
