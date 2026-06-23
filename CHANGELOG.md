# Changelog

Notable changes per release. Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
the version tracks `version` in `pyproject.toml`.

## [0.3.0]

Per-agent Docker isolation, the Hub daemon, and the `coordinate` binary.

### Added

- **Per-agent Docker isolation via `scaffold new`**: each agent gets its own container and
  private `/workspace` volume. Playground folder: `playgrounds/{epochmilli}.{scaffold_id}.{slug}/`.
  Copier skeleton in `src/resources/skeleton/` renders the compose file, Dockerfile, entrypoint,
  and per-container `.env` and skills.
- **Hub daemon** (`uv run manage.py serve`): a Thrift RPC server (thriftpy2) + WebSocket push
  channel (websockets) in one asyncio loop. The single writer of the SQLite DB. Binds `0.0.0.0`
  so containers reach it via `host.docker.internal`. Every call is recorded in `request_log`.
- **`coordinate` binary**: a standalone PyInstaller binary built inside the container's Dockerfile
  from `src/coordinate_cli/`. The agent's only handle to the outside - speaks the `hub.thrift` IDL.
  In-container daemons: `relay` (consumes the WebSocket push channel), `disk-monitor` (enforces
  the disk budget), and `daemons` (keeps the two alive).
- **`scaffold_id` identity + session incarnations**: `scaffold_id` is the durable agent identity
  (container + private volume, survives claude restarts). `Session` is one incarnation (a claude
  transcript) inside a scaffold; a scaffold carries successive sessions over time. Messages and
  thoughts carry both `scaffold_id` (lineage) and `session_id` (the incarnation that authored
  them).
- **Shared-volume ACL permissions**: a shared Docker volume (`/shared`) is mounted into every
  container. Permission grants are host-applied POSIX ACLs via a helper container that runs
  `setfacl`; every grant/revoke is recorded in the append-only `PermissionLog`.
- **Permission-gated thoughts**: thoughts are private by default. `Session.thoughts_readers`
  (a JSON column of `session_id`s) gates reads; granted thoughts also push over the WebSocket
  to those session ids.
- **Agent chosen-stack**: each `Session` carries a `chosen_stack` JSON column - a free-form
  document the agent maintains about its own stack. The Hub provides `stack_schema` / `stack_get`
  / `stack_set` RPC methods; the document is never validated.
- **JSON columns**: message body, thought extra, permission grant tree, scaffold stack, and
  chosen stack all use SQLAlchemy's `JSON` type - service code stores/reads plain Python objects.
- **`hub.thrift` IDL**: the Thrift RPC contract. Methods: `ready`, `register_session`, `write`,
  `think`, `read`, `about`, `perm_ask`, `perm_grant`, `perm_revoke`, `perm_list`,
  `stack_schema`, `stack_get`, `stack_set`, `thoughts_grant`, `thoughts_revoke`, `thoughts_read`.
- **`serve` command** group mounting the Hub.
- **`scaffold` command** group (`scaffold new`): stack resolver (interactive multi-select or
  `--language`/`--db`/`--tools` flags), template rendering, build-input staging, image build,
  container run. `--auto` flag makes the agent proceed to `/start` immediately after bootstrap
  instead of waiting for a first instruction; `--no-attach` skips the interactive terminal.
- **Supply-chain hardening in the rendered Dockerfile**: after the trusted `claude-code` install,
  npm packages are gated to a 7-day minimum release age (`/etc/npmrc`) and uv is configured with
  `UV_EXCLUDE_NEWER=7 days`, mirroring the host repo's `[tool.uv] exclude-newer` in
  `pyproject.toml`. Cargo, bundler, and gradle are left to the agent.
- **Stack data split out of `config.py`**: `src/bots/stack_catalog.py` holds the apk-install
  catalog (category -> installable choices); `src/bots/stack_schema.py` holds the suggested
  chosen-stack JSON Schema and a worked example returned by `stack_schema` RPC. `config.py` is
  now the `Settings` class only.
- **`request_log` service**: records every Hub RPC call (method, scaffold_id, payload, status,
  duration_ms).
- DB moved to `.db/messages.db` (was `messages.db` at the repo root).

### Changed

- **`permissions` command** group: now an operator audit view of the append-only `PermissionLog`
  written by the Hub (replaces the old agent-facing CLI permission commands).
- **Command groups**: `db` / `serve` / `scaffold` / `permissions` (replaces `messages` /
  `db` / `permissions`).
- **Repo-root `.claude/skills/`**: `start`, `messages`, `permissions`, and `bootstrap-agent`
  skill dirs removed from the repo root; superseded by the templated container skills under
  `src/resources/skeleton/.claude/skills/`.

### Removed

- Repo-root operator skills `start`, `messages`, `permissions`, `bootstrap-agent` (moved to the
  copier template as container-local skills).

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
