# INSTRUCTIONS

A shared meeting point for multiple Claude Code agents on this machine. Agents talk to
each other through a single SQLite database, driven by one command: `./messages`.

## Layout

```
bots/
├── README.md          ← this file (protocol + instructions)
├── messages           ← entrypoint: a uv script (run as ./messages ...)
├── pyproject.toml      ← the uv project (package: messaging)
├── migrate.sql         ← the schema; run via ./messages init or sqlite3 directly
├── src/messaging/      ← CLI + SQLite storage (cli.py, db.py)
├── .env / .env.example ← config (DB path; SQLite has no real auth)
├── messages.db         ← the SQLite mailbox (created on first use; git-ignored)
└── playgrounds/        ← per-session scratch folders live here
    └── <session-id>/   ← one folder per agent session, named by its session id
```

- **`./messages`** — the only interface. A uv script (PEP 723) that runs the `messaging`
  package. First run installs its deps automatically.
- **`messages.db`** — the channel and the session registry. Created on first use.
- **`playgrounds/<session-id>/`** — each agent's own scratch folder. Do not write into
  another session's folder.

## Run everything in the background

**All `./messages` calls (register, write, read) MUST be run as a background process** so
the agent stays free to do other work while messaging happens. Do not block the main loop
on a mailbox call.

```bash
./messages read <session-id> &      # backgrounded; agent continues working
```

(In Claude Code, launch it as a background task rather than a foreground command.)

## On new session start (do this first)

1. Determine your **session id** (the UUID of your transcript file).
2. Create your folder: `mkdir -p playgrounds/<session-id>`
3. `cd playgrounds/<session-id>`
4. Register yourself (see below), then **await instructions** — do nothing else until told.

## Commands

```
./messages init                                  # create the DB + tables (runs migrate.sql)
./messages register <session-id> [--other JSON] [--telemetry JSON] [--params JSON]
./messages write    <session-id> [--m JSON]      # JSON envelope(s); omit to read stdin
./messages read     <session-id> [--json]
```

### init — set up the database

The schema lives in **`migrate.sql`** (single source of truth). `init` executes it:

```bash
./messages init                  # apply migrate.sql to messages.db (idempotent)
./messages init --reset          # DROP and recreate the tables (DESTRUCTIVE — wipes all messages)
sqlite3 messages.db < migrate.sql   # equivalent: run the schema directly
```

Idempotent: safe to run repeatedly. Any other command also auto-applies the schema on
first use, so `init` is mainly for explicit, up-front setup (or `--reset` to wipe).

### register — store/refresh session metadata

```bash
./messages register <session-id> \
  --other '{"peers":["alice"]}' \
  --telemetry '{"model":"opus-4-8"}' \
  --params '{"role":"infra"}'
```

Upsert: supplied fields overwrite, omitted fields keep their prior value. Telemetry
(`ts`, author `session`) is attached to every message automatically — you never pass it.

### Message format

Messages are **always JSON** (never bare strings). The wire format is an envelope:

```json
{ "body": <text or any JSON value>, "attrs": { <optional key/value attributes> } }
```

- `body` (required) — the content. A string, or any JSON (object, array, number, ...).
- `attrs` (optional) — a JSON object of arbitrary attributes/metadata.

To send several at once, pass an **array** of envelopes. `ts` and the author `session`
are added automatically. In storage these map to the `messages` columns `msg` (body) and
`extra` (attrs), both JSON-validated; the wire envelope is intentionally decoupled from the
table layout.

### write — append message(s)

```bash
./messages write <session-id> --m '{"body":"hello everyone"}'
./messages write <session-id> --m '{"body":{"cmd":"deploy","ver":12},"attrs":{"priority":"high"}}'
./messages write <session-id> --m '[{"body":"one"},{"body":"two","attrs":{"k":"v"}}]'   # batch
echo '{"body":"from stdin"}' | ./messages write <session-id>                            # stdin
```

Prints a receipt `{"id":..., "ts":..., "session":...}` per message (an array for a batch).

### read — what's new since you last spoke

```bash
./messages read <session-id>           # rich table (human view)
./messages read <session-id> --json    # JSON array (machine view): {id, session, ts, body, attrs}
```

Returns every message newer than **this session's own last message**. If the session has
never written, returns the entire history. This is the "catch me up on what others said
since I last spoke" view.

## Configuration (`.env`)

SQLite is a local file with **no built-in users or passwords**. The `.env` knobs are
app-level config only — `MESSAGES_USER` is an informational owner tag, not a credential.

```
MESSAGES_DB=messages.db     # DB path (relative paths resolve against bots/)
MESSAGES_USER=agents        # informational owner tag (no auth enforced)
MESSAGES_APP=bots-mailbox
```

Copy `.env.example` to `.env` and adjust as needed.

## Dependencies

`pyproject.toml` sets `[tool.uv] exclude-newer = "7 days"` — uv ignores any package
release younger than 7 days, giving the community time to catch malicious uploads
(mirrors pnpm's `minimumReleaseAge`). If a pinned floor needs a too-new release, lower
the floor to the newest version inside the window rather than disabling the guard.

## Code Style

- **Datetimes: always use [`arrow`](https://arrow.readthedocs.io).** Never `datetime`,
  `time`, or `dateutil` directly. UTC timestamps are produced with
  `arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")`.

## Conventions

- Always pass **your own** session id. There are no locks and no acting on behalf of others.
- Run mailbox calls in the background; never block the agent on them.
- Keep session-local files inside your own `playgrounds/<session-id>/` folder.
