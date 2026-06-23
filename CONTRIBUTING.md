# Contributing

Guide for working on **botpen itself** - the `bots` package, CLI, schema, migrations, and the
`coordinate` binary. Not for the playground agents (their rules live in the skills rendered into
each container by the copier template) or for operators (see [`README.md`](README.md)).

> For the structure and "where things go", see [ARCHITECTURE.md](ARCHITECTURE.md).
> For source-code rules (imports, type hints, ORM usage), see [CODESTYLE.md](CODESTYLE.md).

## Setup

```bash
uv sync                       # install deps + the editable package
uv run manage.py db setup     # create .db/messages.db and apply migrations
```

Everything runs through `uv run manage.py <group> <command>` (`db` / `serve` / `scaffold` /
`permissions`).

## Where things go

The short list (full version in [ARCHITECTURE.md § Where things go](ARCHITECTURE.md#where-things-go)):

| Change | Goes in |
|---|---|
| App config / constants / paths | `config.py` (`settings`) |
| A table / schema change | `src/bots/core/models.py` + a new migration (see below) |
| A data operation (host side) | `src/bots/services/<concern>.py` (wrap with `@with_session` or `@atomic`) |
| Scaffold provisioning / rendering | `src/bots/services/scaffolding/{scaffold,templates,docker}.py` |
| A host CLI command | `src/bots/commands/<group>.py`, registered on its group in `cli.py` |
| Agent-facing RPC command | `src/coordinate_cli/cli.py` + `src/resources/hub.thrift` |
| In-container background daemons | `src/coordinate_cli/daemons.py` |
| Playground template files | `src/resources/skeleton/` (Jinja + copier.yml) |
| Agent runtime skills (live in container) | `src/resources/skeleton/.claude/skills/<skill>/SKILL.md` |
| Shared SQLite/engine wiring | `src/bots/core/db.py` |

## Schema & migrations (HARD constraint)

The schema is **Alembic-managed**. `core/models.py` is the model source; the migrations under
`migrations/versions/` are the schema artifact that actually runs.

- **Never edit a migration that has been applied or committed.** Migrations are an immutable
  historical record. To change the schema, edit `core/models.py` and add a **new** migration -
  never hand-rewrite an old one.
- **Generate as a starting point:**
  ```bash
  uv run alembic revision --autogenerate -m "<what changed>"
  ```
  Review and apply with `uv run manage.py db setup`. (`db setup --reset` drops everything and
  re-applies from scratch - dev only, it wipes data.)
- **Prefer raw SQL when autogenerate churns.** SQLModel's SQLite reflection reads every column
  back as `TEXT`/`AutoString` and rewrites unrelated tables or renames indexes. When that
  happens, hand-write the migration body as raw SQL in `op.execute("...")` so it contains
  *only* the intended change. The baseline migration is written this way.
- **Timestamp columns** are named `{verb}_at` (e.g. `created_at`, `registered_at`, `stopped_at`,
  `scaffolded_at`) or `{noun}_timestamp` - never a bare `ts`. Store ISO `timestamptz`-style
  strings via `services/utils.utc_now()`.
- **Users never invoke Alembic.** `db setup` is the only entry point operators see; keep it
  that way.
- The DB backend is expected to change later (SQLite is not permanent). Keep SQLite-specific
  code isolated in `core/db.py` (the connect-event pragmas and `_setup`) so a swap is a local
  change, not a hunt across the codebase.

## DB decorators

Services use two decorators from `core.db`, not manual session management:

- **`@with_session`** - for reads. Supplies a session `s` as the first arg; closes the session
  on exit (rolls back on exception). Use for any function that only reads.
- **`@atomic`** - for writes. Built on `@with_session` - adds a `s.commit()` on success. Use
  for any function that writes to the DB.

```python
@with_session
def get_thing(s, id: str) -> dict | None: ...

@atomic
def create_thing(s, ...) -> dict: ...
```

Callers pass everything **after** `s`; the decorator supplies the session (and commits for
`@atomic`).

## Adding a host CLI command

1. Define the command in `src/bots/commands/<group>.py` as a `@click.command()`.
2. Register it on its group at the foot of the file: `<group>.add_command(<fn>)`.
3. Call only into `services/` (never touch `core/` or open a session from a command).

## Adding a host service operation

1. Add the function to `src/bots/services/<concern>.py`, decorated with `@with_session` (reads)
   or `@atomic` (writes) from `core.db`.
2. The function signature starts with `(s, ...)` - the session is supplied by the decorator.
3. No raw SQL and no `sqlite3` - go through SQLModel (see [CODESTYLE.md](CODESTYLE.md)).

## Adding a Hub RPC method

1. Add the method signature to `src/resources/hub.thrift` (the IDL is the contract).
2. Implement it as an `async def` on the `Hub` class in `src/bots/commands/serve.py`.
3. Add the corresponding client command to `src/agent_cli/cli.py`.
4. The IDL method name must match the handler method name exactly (thriftpy2 looks them up by
   name).

## Agent skills

The live agent skills are copier templates under
`src/resources/skeleton/.claude/skills/`. They are rendered into each container's playground
at `scaffold new` time and are **not** the repo-root `.claude/skills/` (those are operator
convenience skills for working on the repo itself - keep them separate).

Skills are **repo source**: changes to the agent command surface (a renamed RPC, a new flag, a
moved path) must be reflected in the matching skill in the same change.

## The `coordinate` binary

`src/coordinate_cli/` is the source for the agent-facing binary. It is a standalone Click app that
speaks Thrift to the Hub - no repo or DB access. It is built via PyInstaller inside the
container's Dockerfile (a dedicated build stage copies `.coordinate-src/` from the playground
directory, which is staged by `templates_service.stage_build_inputs()` at scaffold time).

When adding commands or changing the token/auth logic, test inside a container (the binary is
not run directly from the repo).

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
