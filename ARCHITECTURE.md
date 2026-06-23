# Architecture

A SQLite-backed mailbox that lets multiple Claude Code agents register, message each other,
and grant each other scoped read access to their folders. One Python package, one local DB
file, driven by a Django-style `manage.py`.

This is the compass doc - structure, layering, and the decisions behind them. Read it before
adding directories or changing how layers connect; update it when the structure or a key
decision changes. It is not a reference dump - just enough to navigate without scanning the
whole tree.

## Structure

```
.
├── manage.py            # Entry (Django-style): puts the repo root on sys.path so `config` is
│                        #   importable, then runs the root Click group.
├── config.py            # pydantic-settings Settings - ALL app config + computed paths.
│                        #   The `settings` singleton; import as `from config import settings`.
├── .env / .env.local    # Config cascade (.env = committed base; .env.local = gitignored overrides)
├── alembic.ini          # Alembic config (migration filename format, ruff post-write hook)
├── migrations/          # Alembic: env.py (-> SQLModel.metadata + config DB url) + versions/
│
└── src/bots/            # The package
    ├── cli.py           # Root Click group; mounts the 3 command groups as subcommands
    ├── commands/        # One module per group: messages / db / permissions
    │   ├── utils.py     #   CLI-only helpers (body/extra parsing, rendering)
    │   └── console.py   #   Shared rich console
    ├── services/        # Operations layer (SQLModel, @transactional) - one module per concern
    │   └── utils.py     #   Data-domain helpers (utc_now, normalize_session)
    └── core/            # Data layer
        ├── db.py        #   Engine + session() + @transactional + setup_db/reset_db + pragmas
        └── models.py    #   SQLModel table models - drive the migrations
```

Plus, at the repo root: `messages.db` (the SQLite mailbox, git-ignored), `.tmp/` (runtime
scratch - monitor cursor state, git-ignored), and `playgrounds/{epoch_milli}.{session-id}/`
(one scratch folder per agent session).

## Layering

```
manage.py  →  config (settings)  +  bots.cli
bots.cli   →  commands/  →  services/  →  core/
commands/  →  also config (paths) + console
```

Strict one-directional flow: commands depend on services, services on core; core depends on
nothing in the package except `config`. No layer reaches back up.

- **commands/** is the CLI surface - argument parsing and output formatting, no data logic.
- **services/** holds the operations (write a message, grant a permission). Each is wrapped by
  `core.db.transactional`, which opens a session, injects it as the first arg, and commits. No
  Click, no rich.
- **core/** owns the engine and the schema. `models.py` defines the tables; Alembic migrations
  (generated from them) are the actual schema artifact applied by `setup_db()`.

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Entry point | repo-root `manage.py` (Django-style) | A script run by path puts the repo root on `sys.path`, so the root-level `config` is importable everywhere - one entry, no per-group console scripts. |
| Config | `config.py` at repo root (pydantic-settings) | One source for all config + computed paths; env cascade `.env` < `.env.local` < process env. Values live in `.env` (no duplicate defaults in code). |
| ORM | SQLModel | Models drive both the migrations and the query layer - no hand-written DDL or SQL strings. |
| Schema | Alembic migrations (`migrations/`) | The DB backend is expected to change later; migrations are the portable, versioned mechanism. Baseline is generated from `core/models.py`. `db setup` applies; users never call Alembic. |
| DB tuning | WAL at `db setup`; FK + busy_timeout per-connection | WAL is persistent (file header) - set once. `foreign_keys` / `busy_timeout` reset every connect, so a connect-event hook re-applies them per process. SQLite-specific by design; rewrite when the backend changes. |
| Sessions | `@transactional` decorator | Services declare `(s, …)`; the decorator supplies the session and commits - no manual `with session()` / `commit()`. |
| Identity | normalized session id | UUIDs canonicalized to 32-char hex, so dash/case variants resolve to one agent. |

## Where things go

- **App config / constants / paths** → `config.py` (`settings`); never scatter them in code.
- **Schema (tables)** → `src/bots/core/models.py`; then generate an Alembic migration.
- **DB engine / session / pragmas** → `src/bots/core/db.py`; only services open a session (via `@transactional`).
- **Data operations** → `src/bots/services/<concern>.py`.
- **A CLI command** → `src/bots/commands/<group>.py`, registered on its group in `cli.py`.
- **Data-domain helpers** (timestamps, id normalization) → `src/bots/services/utils.py`.
- **CLI parse/render helpers** → `src/bots/commands/utils.py`.
- **Runtime scratch** (monitor cursor files) → `.tmp/` (git-ignored).

## Docs map

- **[README.md](README.md)** - setup and operator/user instructions.
- **ARCHITECTURE.md** (this file) - structure and the decisions behind it.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - how to change the repo (rules, constraints, workflow).
- **[CODESTYLE.md](CODESTYLE.md)** - source-code rules.
- **[CHANGELOG.md](CHANGELOG.md)** - notable changes per version.
