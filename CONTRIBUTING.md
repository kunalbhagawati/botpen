# Contributing

Guide for working on **botpen itself** - the `botpen` package, CLI, schema, migrations, and the
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
| A table / schema change | `src/botpen/core/models.py` + a new migration (see below) |
| A data operation (host side) | `src/botpen/services/<concern>.py` (wrap with `@with_session` or `@atomic`) |
| Scaffold provisioning / rendering | `src/botpen/services/scaffolding/{scaffold,templates,docker}.py` |
| A host CLI command | `src/botpen/commands/<group>.py`, registered on its group in `cli.py` |
| Agent-facing RPC command | `src/coordinate_cli/cli.py` + `src/resources/hub.thrift` |
| In-container background daemons | `src/coordinate_cli/daemons.py` |
| Playground template files | `src/resources/skeleton/` (Jinja + copier.yml) |
| Agent runtime skills (live in container) | `src/resources/skeleton/.claude/skills/<skill>/SKILL.md` |
| Shared SQLite/engine wiring | `src/botpen/core/db.py` |

## Coding conventions

The full house style lives in [CODESTYLE.md](CODESTYLE.md) - read it before writing Python here.
The load-bearing principles, in one place:

- **Functions by default; a class only for owned live state.** The service layer is plain
  functions `(s, …) -> data`; the `Hub` is the rare stateful class (it owns the live connections).
- **Let exceptions bubble to a boundary.** `Hub._run` is the RPC boundary, Click is the CLI
  boundary. Catch only to *handle* - never catch-log-reraise. `_run` already records every call
  (success and error) to `request_log`, so services must not pre-log.
- **Annotate signatures, not locals.** Modern syntax only (`X | None`, `list[T]`, PEP 695
  generics); `except A, B:` without parens is intentional 3.14 syntax, not a bug. ruff `UP`
  auto-fixes the rest.
- **Structured JSON events, not logging.** `console` / `click.echo` on the host, `_emit` in
  container daemons. No bare `print()` in `src/botpen/`.
- **One unit, one responsibility; nested functions max depth 1** (the `work(sc)` closures are the
  canonical case).

See [CODESTYLE.md](CODESTYLE.md) for the rest (imports, datetimes, ORM access, type-hint detail,
output sinks).

## Schema & migrations (HARD constraint)

The schema is **Alembic-managed**. `core/models.py` is the model source; the migrations under
`migrations/versions/` are the schema artifact that actually runs.

> [!IMPORTANT]
> **An AI agent MUST NOT create, edit, or delete a migration without explicit human approval.**
> Surface the need - what changed in `core/models.py`, the migration you would generate - and
> **stop**. Never write or apply a migration silently. The schema is the one place where a wrong
> autonomous edit is expensive to unwind, and migrations are an immutable historical record once
> committed.

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

1. Define the command in `src/botpen/commands/<group>.py` as a `@click.command()`.
2. Register it on its group at the foot of the file: `<group>.add_command(<fn>)`.
3. Call only into `services/` (never touch `core/` or open a session from a command).

## Adding a host service operation

1. Add the function to `src/botpen/services/<concern>.py`, decorated with `@with_session` (reads)
   or `@atomic` (writes) from `core.db`.
2. The function signature starts with `(s, ...)` - the session is supplied by the decorator.
3. No raw SQL and no `sqlite3` - go through SQLModel (see [CODESTYLE.md](CODESTYLE.md)).

## Adding a Hub RPC method

The IDL is the contract; both sides compile from it, and the method name is the join key. Every
handler follows the same wrapper contract - keep to it.

1. Add the method signature to `src/resources/hub.thrift` (**edit the IDL first** - it's the
   contract).
2. Implement it as an `async def` on the `Hub` class in `src/botpen/commands/serve.py`, following
   the wrapper contract every other method uses:
   - Define an inner `async def work(sc): …` (a depth-1 closure) holding the actual logic; `sc` is
     the authenticated scaffold row.
   - Return `await self._run("<method>", token, <payload-dict>, work)`. `_run` resolves the token
     to a scaffold, records the call to `request_log` (success **and** error), and JSON-encodes the
     result - so do **not** authenticate, log, or `json.dumps` by hand.
   - **Never block the loop.** Every service / DB call goes through `await asyncio.to_thread(fn, …)`;
     the services are sync and the Hub is the single async DB writer.
3. Add the matching client command to `src/coordinate_cli/cli.py` (the agent-facing binary). It
   calls the Hub via the Thrift client (`client.call`) - it never touches the repo or DB.
4. The IDL method name must match the handler method name exactly (thriftpy2 looks them up by
   name); keep the client command aligned too.
5. If the change alters the agent command surface, update the matching skill under
   `src/resources/skeleton/.claude/skills/` in the **same** change (see [Agent skills](#agent-skills)).

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
