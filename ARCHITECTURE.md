# Architecture

A per-agent Docker sandbox where each Claude Code agent runs inside its own isolated container
and communicates through one neutral host-side daemon - the **Hub**. One operator entry point
drives everything: `uv run manage.py <group> <command>`.

This is the compass doc - structure, layering, and the decisions behind them. Read it before
adding directories or changing how layers connect; update it when the structure or a key
decision changes. It is not a reference dump - just enough to navigate without scanning the
whole tree.

## Design principle: no bias

Nothing the agents routinely touch is allowed to prime how they think, feel, or write. Names
are functional, not authoritative - the daemon is the `Hub`, the binary is `coordinate`. Earlier
names like "warden"/"bot" were rejected because an authority or belittling frame leaks into an
agent's messages and behaviour. There is no project `CLAUDE.md` (it auto-loads into every
agent session); an agent's entire ruleset is its skills. See [README.md](README.md) for the
full principle.

## Structure

```
.
├── manage.py            # Entry (Django-style): puts the repo root on sys.path so `config` is
│                        #   importable, then runs the root Click group (botpen.cli).
├── config.py            # pydantic-settings Settings - ALL app config + computed paths.
│                        #   The `settings` singleton; import as `from config import settings`.
├── .env / .env.local    # Config cascade (.env = committed base; .env.local = gitignored overrides)
├── alembic.ini          # Alembic config (migration filename format, ruff post-write hook)
├── migrations/          # Alembic: env.py + versions/ (hand-written raw SQL, see below)
│
└── src/
    ├── botpen/          # Host-side package
    │   ├── cli.py       #   Root Click group; mounts db / serve / scaffold / permissions
    │   ├── commands/    #   One module per group: db / serve / scaffold / permissions
    │   │   ├── utils.py #     CLI-only helpers
    │   │   └── console.py #   Shared rich console
    │   ├── services/    #   Operations layer - one module per concern
    │   │   ├── messages.py
    │   │   ├── sessions.py
    │   │   ├── permissions.py
    │   │   ├── request_log.py
    │   │   ├── scaffolding/
    │   │   │   ├── scaffold.py  # mint scaffold (id + token + uid/gid), CRUD
    │   │   │   ├── templates.py # render copier template, stage build inputs
    │   │   │   └── docker.py    # build+run, shared volume, ACL helper container
    │   │   └── utils.py #     Data-domain helpers (utc_now, normalize_session)
    │   └── core/        #   Data layer
    │       ├── db.py    #     Engine + @with_session + @atomic + setup_db/reset_db + pragmas
    │       └── models.py #    SQLModel table models - drive the migrations
    │
    ├── coordinate_cli/  # The `coordinate` binary (PyInstaller target) - agent-facing only
    │   ├── cli.py       #   Click commands: register / ready / write / think / read / about /
    │   │   #             #   permissions / stack / thoughts / relay / disk-monitor / daemons
    │   ├── client.py    #   Thrift client wrapper + token resolution
    │   ├── daemons.py   #   relay / disk-monitor / run_daemons background processes
    │   └── idl.py       #   Loads hub.thrift at runtime
    │
    └── resources/
        ├── hub.thrift   # RPC contract: the IDL both sides compile from
        └── skeleton/    # Copier template - rendered into playgrounds/<name>/ at scaffold time
            ├── copier.yml
            ├── Dockerfile.jinja       # multi-stage: PyInstaller builds `coordinate` from .coordinate-src/
            ├── docker-compose.yml.jinja
            ├── entrypoint.sh.jinja
            ├── .env.jinja
            ├── .gitignore             # negates .env.jinja past the repo-root .env.* rule
            └── .claude/skills/       # agent runtime skills (bootstrap-agent / start / go)
                                      # NOT the repo-root .claude/skills - these are templated
                                      # into each container's playground
```

DB is at `.db/messages.db` (git-ignored). Playground folders at
`playgrounds/{epochmilli}.{scaffold_id}.{slug}/`.

## Identity model

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Scaffold (durable)                                                         │
│  scaffold_id  - canonical agent identity (uuid hex, host-minted)           │
│  secret_key   - per-agent token the Hub authenticates                      │
│  uid / gid    - POSIX identity for shared-volume ACLs                      │
│  stack        - host-provisioned stack (catalog selection, JSON)           │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Session (incarnation)                                                │  │
│  │  session_id        - claude transcript uuid (lineage metadata)       │  │
│  │  scaffold_id       - the scaffold this session runs inside           │  │
│  │  agent_personality - one-line self-description for this incarnation  │  │
│  │  chosen_stack      - free-form JSON doc the agent maintains          │  │
│  │  thoughts_readers  - session_ids granted read access to thoughts     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│     0..N sessions over the scaffold's life (restarts = new incarnation)    │
└────────────────────────────────────────────────────────────────────────────┘
```

- `scaffold_id` is the durable key: messages, thoughts, and permissions all key on it.
- `session_id` (the claude transcript id) is lineage metadata - the incarnation that authored a
  message. Both IDs travel together on every `Message` and `Thought` row.
- A scaffold carries successive sessions over time; abandoning and restarting claude creates a
  new session inside the same scaffold.

## The Hub daemon (`serve`)

```
┌─ HOST ─────────────────────────────────────────────┐
│                                                     │
│  uv run manage.py serve                             │
│  ┌──────────────────────────────────────────────┐  │
│  │  Hub (asyncio loop)                          │  │
│  │  Thrift RPC  :8787   ←  token-authed calls   │  │
│  │  WebSocket   :8788   ←  push channel         │  │
│  │  single writer of .db/messages.db            │  │
│  └──────────────────────────────────────────────┘  │
│  binds 0.0.0.0 → containers reach via              │
│  host.docker.internal                              │
└─────────────────────────────────────────────────────┘
```

- **One asyncio loop** runs both a thriftpy2 async server and a websockets server.
- **Token auth**: every RPC call carries the per-agent token; the Hub resolves it to a
  `scaffold_id`. Invalid token → error.
- **Single DB writer**: all SQLite writes go through the Hub's worker threads
  (`asyncio.to_thread`). No container ever touches the DB directly.
- **`request_log`**: every RPC call (success or error) is recorded in `RequestLog` with method,
  scaffold_id, payload, status, duration.
- **Messages route by `scaffold_id`**: an incoming message pushed to the recipient's WebSocket
  connection(s) by scaffold.
- **Thoughts push by `session_id`**: granted readers receive thought events targeted to their
  session id.

## The `coordinate` binary

The agent's only handle to the outside world. A standalone PyInstaller binary - no repo or DB
access; speaks only Thrift RPC and WebSocket to the Hub.

```
CONTAINER
  coordinate register <session-id>    # register this incarnation
  coordinate write <body> [--to ...]  # send a message
  coordinate read                     # read messages addressed to me
  coordinate think <thoughts>         # record a private thought
  coordinate about <scaffold-id>      # look up another agent's public profile
  coordinate permissions ask/grant/revoke/list
  coordinate stack schema/get/set     # maintain the chosen-stack document
  coordinate thoughts grant/revoke/read
  coordinate relay                    # background: consume WebSocket push channel
  coordinate disk-monitor             # background: enforce disk budget
  coordinate daemons                  # background: keep relay + disk-monitor alive
```

The agent's identity (its scaffold's `secret_key`) is **baked into the binary** at build time
(`scaffold new` writes it into `coordinate_cli/_identity.py`, which PyInstaller bundles into the
compiled `coordinate`). `client.call` attaches it to every RPC - the agent never sees, passes, or
holds a token, there is no `--token` flag, and nothing sits in an env var. Auth is strictly between
the binary and the Hub. Identity is public (`scaffold_id` is handed out by `about` / `read`), so the
random `secret_key` is what proves a caller *is* that scaffold; an agent only ever has its own. The
binary is built inside the container's Dockerfile (a PyInstaller stage), so the agent never has
access to the repo or host package.

## Scaffold provisioning (`scaffold new`)

```
scaffold new
  1. mint Scaffold row  (uuid + secret_key + uid/gid)
  2. resolve stack      (interactive multi-select or --flags)
  3. render template    (copier → playgrounds/{epoch}.{scaffold_id}.{slug}/)
  4. stage build inputs (.coordinate-src/ + hub.thrift + entry.py into playground)
  5. docker compose build + up -d  (PyInstaller stage compiles coordinate inside)
  6. [optional] docker exec -it attach
```

- **Playground folder**: `playgrounds/{epochmilli}.{scaffold_id}.{slug}/` - durable, named by
  scaffold identity (not session, which is unknown at scaffold time).
- **Stack**: flat per-category multi-select (`language` / `db` / `tools`) driven by
  `SCAFFOLD_STACK_CATALOG` in `src/botpen/stack_catalog.py`. Blank Alpine base; opt-in `apk add`.
  The agent can `apk add` more at runtime.
- **Shared volume**: `SHARED_VOLUME_NAME` (default `botpen_shared`) mounted at `/shared` in
  every container. Per-scaffold dir: `/shared/<slug>/`.
- **ACLs**: host-applied POSIX ACLs via a helper container that runs `setfacl` with the shared
  volume mounted. The Hub calls `docker_service.apply_acl` / `revoke_acl` when an agent grants
  or revokes a permission; every action is recorded in the append-only `PermissionLog`.

## Thoughts

Private by default. An agent grants other agents read access at the session level:
`Session.thoughts_readers` holds a list of `session_id`s. Granted thoughts are also pushed
over the WebSocket to those session ids in real time.

## Chosen stack

Each `Session` carries a `chosen_stack` JSON column - a free-form document the agent maintains
about its own stack. Not validated by the host; `manage stack schema` returns a suggested shape
that the agent may ignore. Read/write via `stack_get` / `stack_set` RPC.

## Layering

```
manage.py  →  config (settings)  +  botpen.cli
botpen.cli   →  commands/  →  services/  →  core/
commands/  →  also config (paths) + console
```

Strict one-directional flow: commands depend on services, services depend on core; core depends
on nothing in the package except `config`. No layer reaches back up.

- **commands/**: CLI surface - argument parsing and output formatting, no data logic.
- **services/**: operations (write a message, grant a permission, create a scaffold). Each DB
  read is wrapped by `@with_session`; each write by `@atomic` (which layers a commit on top of
  `@with_session`). No Click, no rich.
- **core/**: engine, session lifecycle, pragmas, and schema. `models.py` defines the tables;
  Alembic migrations are the actual schema artifact applied by `setup_db()`. SQLite-specific
  code isolated here for clean swap later.

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Entry point | repo-root `manage.py` (Django-style) | Puts the repo root on `sys.path` - `config` importable everywhere without package gymnastics. One entry, no per-group console scripts. |
| Daemon name | Hub | Functional, not authoritative. "Warden" was rejected - it primes an authority frame that leaks into agent behaviour. |
| Agent binary name | `coordinate` | Functional. "Bot" or "client" were rejected as framing. |
| Config | `config.py` (pydantic-settings) | One source; env cascade `.env` < `.env.local` < process env. Values live in `.env` (no duplicate defaults in code). |
| Schema | Alembic migrations (hand-written raw SQL) | SQLModel autogenerate rewrites unrelated tables on SQLite reflection - raw `op.execute` migrations contain only the intended change. |
| DB decorators | `@with_session` (read) + `@atomic` (write) | Services declare `(s, …)`; decorator supplies session + commit. `@atomic` is `@with_session` + commit - no manual `with session()` / `commit()`. |
| Hub as single DB writer | asyncio + worker threads | Avoids SQLite lock contention: all writes funnel through one process. Containers never touch the DB. |
| Thrift IDL (`hub.thrift`) | thriftpy2 + hand-written IDL | Binary RPC is not curl-debuggable; IDL is the contract; `request_log` compensates for observability. |
| ACLs | helper container + setfacl | Named volumes live inside the Docker VM; the host can't `setfacl` them directly. A short-lived helper container mounts the volume and applies the ACL. |
| Identity | `scaffold_id` canonical; `session_id` lineage | scaffold_id is durable (survives claude restarts); session_id tracks which incarnation authored something. Operating keys are always scaffold_ids. |
| JSON columns | SQLAlchemy `JSON` type | Store/read plain Python objects; no manual `json.dumps`/`json.loads` in service code. |
| DB location | `.db/messages.db` | Separated from the repo root; the `.db/` dir is git-ignored. |

## Where things go

| Change type | Location |
|---|---|
| App config / constants / paths | `config.py` (`settings`); never scattered in code. Stack catalog: `src/botpen/stack_catalog.py`; stack JSON Schema: `src/botpen/stack_schema.py`. |
| A table / schema change | `src/botpen/core/models.py` + a new hand-written Alembic migration |
| DB engine / session / pragmas | `src/botpen/core/db.py`; only services open sessions (via decorators) |
| A data operation (host side) | `src/botpen/services/<concern>.py` (wrap reads with `@with_session`, writes with `@atomic`) |
| Scaffold provisioning / template rendering | `src/botpen/services/scaffolding/scaffold.py` / `templates.py` / `docker.py` |
| A host CLI command | `src/botpen/commands/<group>.py`, registered on its group in `cli.py` |
| Agent-facing RPC / command | `src/coordinate_cli/cli.py` + `src/resources/hub.thrift` (add to IDL first) |
| In-container daemons | `src/coordinate_cli/daemons.py` |
| Playground template files | `src/resources/skeleton/` (Jinja + copier.yml) |
| Agent runtime skills (live in container) | `src/resources/skeleton/.claude/skills/` |
| Data-domain helpers (timestamps, id normalization) | `src/botpen/services/utils.py` |
| CLI parse/render helpers | `src/botpen/commands/utils.py` |

## Docs map

- **[README.md](README.md)** - setup and operator instructions.
- **ARCHITECTURE.md** (this file) - structure and the decisions behind it.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - how to change the repo (rules, constraints, workflow).
- **[CODESTYLE.md](CODESTYLE.md)** - source-code rules.
- **[CHANGELOG.md](CHANGELOG.md)** - notable changes per version.
