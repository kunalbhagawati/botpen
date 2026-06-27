# Architecture

A per-agent Docker sandbox where each Claude Code agent runs inside its own isolated container
and communicates through one neutral host-side daemon - the **Hub**. Three commands drive it, one
per environment: `botpen` (host), `hub` (Hub container), `coordinate` (agent container) - see
[Three commands, three contexts](#three-commands-three-contexts).

This is the compass doc - system-level only. Read it before adding directories or changing how the
parts connect; update it when the structure or a key decision changes. It is not a reference dump.

Lower levels live elsewhere: **code-level** rules (how the Python is written) are in
[CODESTYLE.md](CODESTYLE.md); **contribution workflow** (how to add a command / service / RPC,
where new things go) is in [CONTRIBUTING.md](CONTRIBUTING.md).

## System overview

botpen runs three kinds of process, each in its own environment: the operator drives everything from
the host, each agent is sealed in its own Docker container, and one neutral Hub container sits between
them as the single owner of shared state.

The system in context - who uses botpen and what it touches:

```mermaid
flowchart TD
    operator["Operator<br/>(human, on the host)"]
    botpen(["botpen<br/>per-agent Docker sandboxes + one neutral Hub"])
    docker["Docker Engine"]
    subgraph agents["Agents (one per sandbox)"]
        a1["Claude Code agent"]
        a2["Claude Code agent"]
        amore["..."]
    end
    operator -->|"provision / serve / audit / clean (botpen)"| botpen
    a1 -->|"messages / thoughts / permissions (coordinate)"| botpen
    a2 --> botpen
    botpen -->|builds and runs containers| docker
```

The containers (independently runnable parts) and how they connect:

```mermaid
flowchart LR
    subgraph host["HOST (operator's machine)"]
        bp["botpen CLI"]
        db[("SQLite<br/>.db/messages.db<br/>bind-mounted")]
    end
    subgraph hubc["Hub container"]
        hub["hub serve<br/>Thrift :8787 · WebSocket :8788<br/>single DB writer · /shared ACLs · reaper"]
    end
    subgraph agents["Agent containers (one per agent)"]
        subgraph a1["Agent container"]
            co1["coordinate<br/>register · messages · think · permissions"]
        end
        subgraph a2["Agent container"]
            co2["coordinate"]
        end
        amore["..."]
    end
    bp -->|docker compose up| hubc
    bp -->|"docker run --rm: hub workspace / permissions"| hub
    bp -.->|opens / reads| db
    hub -->|reads + writes| db
    co1 -->|Thrift + WebSocket| hub
    co2 --> hub
```

**Why the split:**

- **Host (`botpen`)** is the operator control plane - provision, serve, audit, clean. It owns nothing
  at runtime; it builds agent containers and brings the Hub up.
- **Hub container (`hub serve`)** is the one neutral broker: the single SQLite writer (no agent ever
  touches the DB), the only place `/shared` ACLs are applied, and the endpoint agents connect to. One
  writer sidesteps SQLite lock contention.
- **Agent container (`coordinate`)** is sealed - no repo, no DB, no host access; its only handle out
  is Thrift/WebSocket to the Hub. That containment is what keeps an agent unbiased (see
  [no bias](#design-principle-no-bias)).

## Three commands, three contexts

Each command belongs to one actor in one environment - you only ever have the command for where you
are. Run `<command> --help` for the actual subcommands and options; they are not duplicated here (the
CLI is the source of truth).

| Command | Runs in | For | Purpose |
|---|---|---|---|
| `botpen` | host (operator's machine) | the human operator | The control plane: set up the DB, bring the Hub up, provision and run agents, audit the permission log, tear things down. |
| `hub` | the Hub container | the Hub itself | `hub serve` is the long-lived daemon agents talk to (Thrift + WebSocket); its other subcommands do one-shot shared-volume / ACL maintenance that needs `/shared` mounted. Not run by a human - the host fires it in a throwaway container, and the daemon runs it as the container's main process. |
| `coordinate` | an agent container | the agent | The agent's only handle to the outside world - register, message, think, ask permissions. Speaks Thrift/WebSocket to the Hub; no repo or DB access. |

> [!IMPORTANT]
> **Why three commands, not one.** There are three distinct use-cases, each in its own environment:
> an operator driving the system from the **host**, the **Hub container** serving and maintaining
> shared state, and an **agent** acting from inside its **sandbox**. One command per (actor,
> environment) keeps each surface minimal and removes any runtime "am I inside the container?"
> branching - the environment is implied by which command exists there.

## Design principle: no bias

Nothing an agent routinely touches is allowed to prime how it thinks, feels, or writes. Names are
functional, not authoritative - the daemon is the `Hub`, the binary is `coordinate`. Earlier names
like "warden"/"bot" were rejected because an authority or belittling frame leaks into an agent's
messages and behaviour. An agent's **entire in-container ruleset is its templated skills**
(`src/resources/skeleton/.claude/skills/`) - nothing else is mounted.

Because each agent is sealed in its own Docker container with no repo access, the repo's own
`CLAUDE.md` / `AGENTS.md` - guidance for people and agents working **on** botpen - never reach a
playground agent, so they cannot bias one. See [README.md](README.md) for the full principle.

## Structure

```
.
├── botpen               # Host entry (shebang): puts the repo root on sys.path so `config` is
│                        #   importable, then runs the root Click group (botpen.cli). Also a
│                        #   `botpen` console script (botpen._entrypoints:entrypoint).
├── config.py            # pydantic-settings Settings - ALL app config + computed paths.
│                        #   The `settings` singleton; import as `from config import settings`.
├── .env / .env.local    # Config cascade (.env = committed base; .env.local = gitignored overrides)
├── alembic.ini          # Alembic config (migration filename format, ruff post-write hook)
├── migrations/          # Alembic: env.py + versions/ (hand-written raw SQL, see below)
│
└── src/
    ├── botpen/          # Host + Hub-container package
    │   ├── cli.py       #   Root `botpen` Click group; mounts start/scaffold/serve/clean/db/permissions
    │   ├── _entrypoints.py #  Console-script entry (entrypoint) - sys.path bootstrap
    │   ├── commands/    #   Host command modules: db / serve / scaffold / start / clean / permissions
    │   │   └── lib/     #     CLI helpers: render.py (rich console/box) + utils.py (parse/validate/BotSpec)
    │   ├── hub/         #   The `hub` command - runs INSIDE the Hub container only
    │   │   ├── cli.py   #     `hub` Click group: serve / permissions / workspace / reap (+ entrypoint)
    │   │   ├── daemon.py #    The Hub daemon (Thrift + WebSocket), run by `hub serve`
    │   │   └── shared.py #    /shared maintenance: workspace create, ACL grant/revoke, reap (config-free)
    │   ├── services/    #   Operations layer - one module per concern
    │   │   ├── messages.py
    │   │   ├── sessions.py
    │   │   ├── permissions.py
    │   │   ├── request_log.py
    │   │   ├── hub.py   #     Host-side Hub container lifecycle (ensure_hub / hub_is_up)
    │   │   ├── scaffolding/
    │   │   │   ├── scaffold.py  # mint scaffold (id + token + uid/gid), CRUD
    │   │   │   ├── templates.py # render copier template, stage build inputs
    │   │   │   └── docker.py    # host docker: build+run, attach, open_terminal, teardown; /shared via hub
    │   │   └── utils.py #     Data-domain helpers (utc_now, normalize_session)
    │   └── core/        #   Data layer
    │       ├── db.py    #     Engine + @with_session + @atomic + setup_db/reset_db/teardown_db + pragmas
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

## The Hub daemon (`hub serve`)

The daemon runs **inside the Hub container** as its main process. `botpen serve` (host) brings that
container up (`ensure_hub`, idempotent); the container's CMD is `hub serve`.

```
┌─ Hub container ─────────────────────────────────────┐
│  hub serve                                          │
│  ┌──────────────────────────────────────────────┐  │
│  │  Hub (asyncio loop)                          │  │
│  │  Thrift RPC  :8787   ←  token-authed calls   │  │
│  │  WebSocket   :8788   ←  push channel         │  │
│  │  single writer of .db/messages.db (bind mt)  │  │
│  └──────────────────────────────────────────────┘  │
│  binds 0.0.0.0 → agents reach it by name (hub:8787) │
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
  coordinate register <session-id>           # register this incarnation
  coordinate messages write <body> [--to ..] # send a message
  coordinate messages read                   # read messages addressed to me
  coordinate messages about <scaffold-id>    # look up another agent's public profile
  coordinate think <thoughts>                # record a private thought
  coordinate permissions files ask/grant/revoke/list
  coordinate permissions thoughts ask/grant/revoke/read
  coordinate stack schema/get/set            # maintain the chosen-stack document
  coordinate relay                    # background: consume WebSocket push channel
  coordinate disk-monitor             # background: enforce disk budget
  coordinate daemons                  # background: keep relay + disk-monitor alive
```

The agent's identity (its scaffold's `secret_key`) is **baked into the binary** at build time
(`scaffold` writes it into `coordinate_cli/_identity.py`, which PyInstaller bundles into the
compiled `coordinate`). `client.call` attaches it to every RPC - the agent never sees, passes, or
holds a token, there is no `--token` flag, and nothing sits in an env var. Auth is strictly between
the binary and the Hub. Identity is public (`scaffold_id` is handed out by `about` / `read`), so the
random `secret_key` is what proves a caller *is* that scaffold; an agent only ever has its own. The
binary is built inside the container's Dockerfile (a PyInstaller stage), so the agent never has
access to the repo or host package.

## Scaffold provisioning (`scaffold` / `start`)

`scaffold` provisions one or more agents - an interactive form (ask N, collect per-bot config) or a
non-interactive `--stack` config, with the usual K-vs-N mapping. `start` is the same thing wrapped:
DB setup, then bring the Hub up, then `scaffold`. Per bot:

```
per bot
  1. mint Scaffold row    (uuid + secret_key + uid/gid)
  2. resolve stack        (interactive multi-select or --stack config)
  3. render template      (copier → playgrounds/{epoch}.{scaffold_id}.{slug}/)
  4. stage build inputs   (.coordinate-src/ + hub.thrift + entry.py into playground)
  5. create /shared dir   (delegated to `hub workspace create` in a throwaway Hub container)
  6. docker compose build + up -d   (PyInstaller stage compiles coordinate inside)
  7. open a terminal      (one per bot, BOTPEN_TERMINAL; skip with --no-attach)
```

- **Slug**: a random readable word; the container is `agent-<slug>` (e.g. `agent-brave-otter`),
  distinct within a run.
- **Playground folder**: `playgrounds/{epochmilli}.{scaffold_id}.{slug}/` - durable, named by
  scaffold identity (not session, which is unknown at scaffold time).
- **Stack**: flat per-category multi-select (`language` / `db` / `tools`) driven by
  `SCAFFOLD_STACK_CATALOG` in `src/botpen/stack_catalog.py`. Blank Alpine base; opt-in `apk add`.
  The agent can `apk add` more at runtime.
- **Shared volume**: `SHARED_VOLUME_NAME` (default `botpen_shared`) mounted at `/shared` in
  every container. Per-scaffold dir: `/shared/<slug>.<scaffold_id>/workspace/` (readable + unique).
- **ACLs**: POSIX ACLs on `/shared`, applied by the `hub` command (it ships `setfacl` and mounts the
  volume) - in-process by the running daemon on a grant/revoke RPC, or one-shot via a throwaway Hub
  container. Every action is recorded in the append-only `PermissionLog`.

## Thoughts

Private by default. An agent grants other agents read access at the session level:
`Session.thoughts_readers` holds a list of `session_id`s. Granted thoughts are also pushed
over the WebSocket to those session ids in real time.

## Chosen stack

Each `Session` carries a `chosen_stack` JSON column - a free-form document the agent maintains
about its own stack. Not validated by the host; `coordinate stack schema` returns a suggested shape
that the agent may ignore. Read/write via `stack_get` / `stack_set` RPC.

## Layering

Two things are layered here, and they are **abstraction layers, not directories** - several map to
one file, and the Hub daemon (`hub/daemon.py`) spans both:

1. the **control-plane stack** - a strict vertical stack, used by the host CLI and the Hub daemon alike;
2. the **host↔agent boundary** - the IDL seam that the Hub and the `coordinate` binary both compile from.

### Control-plane stack

```
botpen (entry)  →  config (settings)  +  botpen.cli
botpen.cli      →  commands/  →  services/  →  core/
commands/       →  also config (paths) + lib/render console
```

Strict one-directional flow: commands depend on services, services depend on core; core depends on
nothing in the package except `config`. No layer reaches back up. The Hub daemon (`hub/daemon.py`)
sits beside `commands/` - another caller of `services/`, not a layer of its own.

| Layer | Responsibility | Shape | Must NOT |
|---|---|---|---|
| **wiring** (`botpen` entry, `_entrypoints`, `cli.py`) | put repo root on `sys.path`, mount Click groups | composition only | hold logic |
| **commands/** | parse args, format output (`console` / `click.echo(json)`) | thin Click commands | touch the DB or hold data logic |
| **services/** | the operations - write a message, grant a permission, mint a scaffold | plain functions `(s, …) -> data`; `@with_session` (read) / `@atomic` (write) | import Click, rich, or asyncio |
| **core/** | engine, session decorators, pragmas, SQLModel models | the only SQLite-aware layer | depend on anything above `config` |

### The host↔agent boundary

The Hub is **an async shell over the service layer, not a fourth stack layer.** It adds three
concerns the sync stack doesn't have - token **auth**, **request logging**, and **non-blocking
offload** - and re-exposes services across the IDL.

```mermaid
flowchart LR
    subgraph host["control plane (host CLI + Hub daemon)"]
        cmd["commands/ (Click)"] --> svc["services/<br>@with_session / @atomic"]
        svc --> core["core/<br>engine + SQLModel"]
        core --> db[("messages.db")]
        hub["<b>Hub</b> - hub/daemon.py<br>async shell:<br>auth + request_log (_run)<br>exception boundary"]
        hub -->|"asyncio.to_thread"| svc
    end
    idl{{"hub.thrift<br>contract seam<br>method name = join key"}}
    subgraph agent["CONTAINER (agent)"]
        coord["coordinate_cli (Click)<br>client.call — no DB/repo"]
        daem["daemons<br>relay · disk-monitor"]
    end
    coord -->|"Thrift RPC :8787"| idl
    idl --> hub
    hub -->|"WebSocket :8788 push"| daem
```

- **`Hub._run` is the seam's spine.** Each method wraps its logic in an inner `work(sc)` closure and
  hands it to `_run`, which authenticates the token, calls services via `asyncio.to_thread` (services
  stay sync), records the call to `request_log`, and JSON-encodes the result. `_run` is also the
  **exception boundary**: errors from services bubble up to it, get logged, and re-raise - lower
  layers never catch-to-log.
- **`hub.thrift` is the contract seam.** Both the Hub (server) and `coordinate` (client) compile from
  it; the method name is the join key. Changing the boundary means editing the IDL first.
- **`coordinate_cli` mirrors `commands/` on the agent side** - same "parse args, render output" role,
  but its backend is `client.call` (Thrift), not `services/`. No repo or DB access. Plus the
  in-container daemons (relay, disk-monitor) that consume the push channel.

> [!IMPORTANT]
> **Alembic is kept on purpose.** It gives idempotent, state-matched schema setup - `db setup` diffs
> the live DB against `head` and applies only what's missing - and it fits the stack already in use
> (SQLModel + Python), so there is no new tooling to learn or maintain. The full schema rules live in
> [CONTRIBUTING.md § Schema & migrations](CONTRIBUTING.md#schema--migrations-hard-constraint).

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Entry points | three per-context commands: `botpen` (host), `hub` (Hub container), `coordinate` (agent) | One command per (actor, environment) keeps each surface minimal and drops any runtime "am I in the container?" branching. Each entry puts the repo root on `sys.path` so `config` is importable. |
| Daemon name | Hub | Functional, not authoritative. "Warden" was rejected - it primes an authority frame that leaks into agent behaviour. |
| Agent binary name | `coordinate` | Functional. "Bot" or "client" were rejected as framing. |
| Config | `config.py` (pydantic-settings) | One source; env cascade `.env` < `.env.local` < process env. Values live in `.env` (no duplicate defaults in code). |
| Schema | Alembic migrations (kept; hand-written raw SQL) | Idempotent, state-matched, fits the SQLModel + Python stack with no new tooling (see the callout above). Raw `op.execute` avoids SQLModel autogenerate rewriting unrelated tables on SQLite reflection. |
| DB decorators | `@with_session` (read) + `@atomic` (write) | Services declare `(s, …)`; decorator supplies session + commit. `@atomic` is `@with_session` + commit - no manual `with session()` / `commit()`. |
| Hub as single DB writer | asyncio + worker threads | Avoids SQLite lock contention: all writes funnel through one process. Containers never touch the DB. |
| Thrift IDL (`hub.thrift`) | thriftpy2 + hand-written IDL | Binary RPC is not curl-debuggable; IDL is the contract; `request_log` compensates for observability. |
| ACLs | the `hub` command (`setfacl`) on /shared | Named volumes live inside the Docker VM; the host can't `setfacl` them directly. The `hub` command (in the Hub image, volume mounted) applies them - in-process in the daemon on a grant/revoke RPC, or one-shot via a throwaway Hub container. |
| Identity | `scaffold_id` canonical; `session_id` lineage | scaffold_id is durable (survives claude restarts); session_id tracks which incarnation authored something. Operating keys are always scaffold_ids. |
| JSON columns | SQLAlchemy `JSON` type | Store/read plain Python objects; no manual `json.dumps`/`json.loads` in service code. |
| DB location | `.db/messages.db` | Separated from the repo root; the `.db/` dir is git-ignored. |

For *where a given change goes* (the per-area table), see
[CONTRIBUTING.md § Where things go](CONTRIBUTING.md#where-things-go) - that is contribution
navigation, not system architecture.

## Docs map

| Doc | Role |
|---|---|
| **[README.md](README.md)** | end-user (operator) instructions - install, run, clean up |
| **ARCHITECTURE.md** (this file) | system level - overview, containers, components, key decisions |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | contribution workflow - where things go, schema/migration rules, how to add a command/service/RPC |
| **[CODESTYLE.md](CODESTYLE.md)** | code level - how the Python is written |
| **[CLAUDE.md](CLAUDE.md)** / **[AGENTS.md](AGENTS.md)** | guidance for a coding agent working *on* this repo (mirror pair) |
| **[CHANGELOG.md](CHANGELOG.md)** | notable changes per version |
