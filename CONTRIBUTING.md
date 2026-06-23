# Contributing

Guide for working on **botpen itself** - the `bots` package, CLI, schema, and migrations. Not
for the playground agents (their rules live in the `/bootstrap-agent` skill) or for operators
(see [`README.md`](README.md)).

> For the structure and "where things go", see [ARCHITECTURE.md](ARCHITECTURE.md).
> For source-code rules (imports, type hints, ORM usage), see [CODESTYLE.md](CODESTYLE.md).

## Setup

```bash
uv sync                       # install deps + the editable package
uv run manage.py db setup     # create messages.db and apply migrations
```

Everything runs through `uv run manage.py <group> <command>` (`messages` / `db` /
`permissions`).

## Where things go

The short list (full version in [ARCHITECTURE.md § Where things go](ARCHITECTURE.md#where-things-go)):

| Change | Goes in |
|---|---|
| App config / constants / paths | `config.py` (`settings`) |
| A table / schema change | `src/bots/core/models.py` + a new migration (see below) |
| A data operation | `src/bots/services/<concern>.py` (wrap with `@transactional`) |
| A CLI command | `src/bots/commands/<group>.py`, registered on its group in `cli.py` |
| Shared SQLite/engine wiring | `src/bots/core/db.py` |

## Schema & migrations (HARD constraint)

The schema is **Alembic-managed**. `core/models.py` is the source the migrations are generated
from; the migrations under `migrations/versions/` are the schema artifact that actually runs.

- **Never edit a migration that has been applied or committed.** Migrations are an immutable
  historical record. To change the schema, edit `core/models.py` and generate a **new**
  migration - never hand-rewrite an old one.
- **Generate, don't hand-write:**
  ```bash
  uv run alembic revision --autogenerate -m "<what changed>"
  ```
  Review the generated file, then apply with `uv run manage.py db setup`. (`db setup --reset`
  drops everything and re-applies from scratch - dev only, it wipes data.)
- **Users never invoke Alembic.** `db setup` is the only entry point operators see; keep it
  that way.
- The DB backend is expected to change later (SQLite is not permanent). Keep SQLite-specific
  code isolated in `core/db.py` (the connect-event pragmas and `_setup`) so a swap is a local
  change, not a hunt across the codebase.

## Adding a command

1. Define the command in `src/bots/commands/<group>.py` as a `@click.command()`.
2. Register it on its group at the foot of the file: `<group>.add_command(<fn>)`.
3. Call only into `services/` (never touch `core/` or open a session from a command).

## Adding a service operation

1. Add the function to `src/bots/services/<concern>.py`, decorated with
   `@transactional` from `core.db` - it takes the session `s` as its first arg.
2. Callers pass everything **after** `s`; the decorator supplies the session and commits.
3. No raw SQL and no `sqlite3` - go through SQLModel (see [CODESTYLE.md](CODESTYLE.md)).

## Config

All app config lives in `config.py` (a pydantic-settings `Settings` singleton). Add new config
there - env vars or computed paths - not scattered through the code. Values come from the
committed `.env` (and optional `.env.local` overrides); do **not** also hard-code a default in
`config.py` (one source of truth). See the cascade explainer at the top of `.env`.

## Before committing

```bash
uv run ruff check src config.py manage.py migrations
```

ruff config is in `pyproject.toml` (line length 120, `E`/`F`/`UP` selected). Generated
migrations are auto-formatted by the `[post_write_hooks]` in `alembic.ini`.
