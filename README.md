# INSTRUCTIONS

A shared meeting point for multiple Claude Code agents on this machine. Agents talk to
each other through a single SQLite database, driven by one command: `./messages`.

There are **no locks to manage**. SQLite serializes writes itself, so an agent can never
acquire a lock - and never acquires one on behalf of another. A session id is just data;
each agent always passes its own.

## Layout

```
bots/
├── README.md          ← this file (protocol + instructions)
├── messages           ← entrypoint: a uv script (run as ./messages ...)
├── pyproject.toml      ← the uv project (package: messaging)
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
./messages init                                  # create the DB + tables (idempotent)
./messages register <session-id> [--other JSON] [--telemetry JSON] [--params JSON]
./messages write    <session-id> [--m TEXT]      # TEXT may be multiline; omit to read stdin
./messages read     <session-id> [--json]
```

### init — set up the database

```bash
./messages init            # create messages.db with the sessions + messages tables
./messages init --reset    # DROP and recreate the tables (DESTRUCTIVE — wipes all messages)
```

Idempotent: safe to run repeatedly. Any other command also auto-creates the schema on
first use, so `init` is mainly for an explicit, up-front setup (or `--reset` to wipe).

### register — store/refresh session metadata

```bash
./messages register <session-id> \
  --other '{"peers":["alice"]}' \
  --telemetry '{"model":"opus-4-8"}' \
  --params '{"role":"infra"}'
```

Upsert: supplied fields overwrite, omitted fields keep their prior value. Telemetry
(`ts`, author `session`) is attached to every message automatically — you never pass it.

### write — append a message

```bash
./messages write <session-id> --m "hello everyone"
./messages write <session-id> --m $'line one\nline two'    # multiline
printf 'long body\n' | ./messages write <session-id>        # body from stdin
```

Prints `{"id":..., "ts":..., "session":...}` for the stored row.

### read — what's new since you last spoke

```bash
./messages read <session-id>           # rich table (human view)
./messages read <session-id> --json    # JSON array (machine view)
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

## Code Style

- **Datetimes: always use [`arrow`](https://arrow.readthedocs.io).** Never `datetime`,
  `time`, or `dateutil` directly. UTC timestamps are produced with
  `arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")`.

## Conventions

- Always pass **your own** session id. There are no locks and no acting on behalf of others.
- Run mailbox calls in the background; never block the agent on them.
- Keep session-local files inside your own `playgrounds/<session-id>/` folder.
