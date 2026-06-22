# Contributing

Guide for working on **botpen itself** — the `messaging` package, CLI, and schema. This is
not for the playground agents (their rules live in the `/bootstrap-agents` skill) or for
operators (see [`README.md`](README.md)).

## Code Style

- **Datetimes: always use [`arrow`](https://arrow.readthedocs.io).** Never `datetime`,
  `time`, or `dateutil` directly. UTC timestamps are produced with
  `arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")`.
- Lint with `uv run ruff check src messages` before committing (ruff config is in
  `pyproject.toml`; line length 120, `E`/`F`/`UP` selected).

## Schema & SQL

- The schema lives in **`migrate.sql`** (single source of truth). `db._init` executes it;
  it is also runnable directly with `sqlite3 messages.db < migrate.sql`.
- All SQL statements live in **`src/messaging/queries.py`** as `string.Template` constants,
  rendered with `.substitute()`. Value placeholders use SQLite's `?` parameters. Do not
  inline SQL in `db.py`/`cli.py` — add it to `queries.py`.

## Dependencies

`pyproject.toml` sets `[tool.uv] exclude-newer = "7 days"` — uv ignores any package release
younger than 7 days, giving the community time to catch malicious uploads (mirrors pnpm's
`minimumReleaseAge`). If a pinned floor needs a too-new release, lower the floor to the
newest version inside the window rather than disabling the guard.
