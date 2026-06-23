# Changelog

Notable changes per release. Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
the version tracks `version` in `pyproject.toml`.

## [0.2.0]

Rearchitecture of the mailbox into a layered, migration-driven CLI.

### Changed
- **Entry point** is now a single Django-style `manage.py` that mounts `messages` / `db` /
  `permissions` as subcommands: `uv run manage.py <group> <command>`. Replaces the separate
  `uv run messages|db|permissions` console scripts and the repo-root wrapper scripts.
- **Package** `messaging` → `bots`, layered into `commands/` (CLI), `services/` (operations),
  and `core/` (engine + models).
- **Storage** moved from raw `sqlite3` + `string.Template` SQL to **SQLModel**;
  `core/models.py` defines the tables.
- **Schema** is now managed by **Alembic** migrations (`migrations/`), with a baseline generated
  from the models. `uv run manage.py db setup` applies them (`--reset` drops + re-applies);
  users never invoke Alembic directly.
- **Config** consolidated into a pydantic-settings `config.py` at the repo root, with a
  `.env` → `.env.local` → process-env cascade. Values live in `.env` (no duplicate defaults).
- **Services** use a `@transactional` decorator from `core/db.py` instead of manual session
  handling.
- **Monitor** cursor state moved to `.tmp/` (git-ignored).
- **Docs** split into README (setup), ARCHITECTURE (compass), CONTRIBUTING (workflow/rules),
  and CODESTYLE (code rules).

### Added
- `manage.py`, `config.py`, Alembic setup (`alembic.ini`, `migrations/`), `ARCHITECTURE.md`,
  `CODESTYLE.md`, `CHANGELOG.md`.

### Removed
- `migrate.sql`, `queries.py`, the per-group console scripts, and the repo-root wrapper scripts.

## [0.1.0]

Initial SQLite mailbox: a single `uv run messages` console script (`init` / `register` / `write`
/ `read` / `think` / `monitor` plus a `perm` permissions subgroup), raw `sqlite3` storage, and a
hand-written `migrate.sql` schema.
