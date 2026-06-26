# botpen

> [!IMPORTANT]
> **`CLAUDE.md` and `AGENTS.md` are a mirror pair — you MUST keep them identical.** Any edit to this
> file MUST be applied to [`AGENTS.md`](AGENTS.md) in the **same** commit, and vice versa. Never
> change one without the other — a one-sided edit is a defect, not a partial update.
>
> **Naming one means both.** When an instruction refers to only one file — e.g. "update CLAUDE.md
> …" — it ALWAYS implicitly means the other too. Apply the change to [`AGENTS.md`](AGENTS.md) as
> well, every time, without being asked.
>
> The only permitted difference is vendor-specific bits (Claude Code skills / hooks / MCP) that
> don't apply to the generic [agents.md](https://agents.md) spec. This file follows the
> [Claude Code memory format](https://code.claude.com/docs/en/memory#claude-md-files).

Guidance for a coding agent working **on the botpen repo itself** - the `botpen` host package, the
`coordinate` binary, the scaffolding, schema, and migrations.

## Scope

- Applies to the whole repo unless a deeper `AGENTS.md` overrides it.
- **This file is for working on botpen, not for the playground agents.** It is never mounted into a
  playground container - an agent running *inside* botpen gets only its templated skills
  (`src/resources/skeleton/.claude/skills/`), by design (see the no-bias principle in
  [ARCHITECTURE.md](ARCHITECTURE.md#design-principle-no-bias)). Editing this file cannot bias them.

## Project overview

botpen is a per-agent Docker sandbox: each Claude Code agent runs in its own isolated container and
talks to one neutral Hub - a container running `hub serve` - through a single in-container binary,
`coordinate` (Thrift RPC + WebSocket). Three commands, one per environment: the operator drives
everything from the host with `botpen` (`uv run botpen <group> <command>` or `./botpen …`); inside
the Hub container the command is `hub`; inside an agent container it is `coordinate`.

## Required reading — ALWAYS read these

Before writing or modifying any code you MUST read these in full. Don't work from a summary or from
memory — they are the source of truth, and this file deliberately does **not** restate them (a copy
here would only drift). Read the files themselves; don't pre-emptively chase every link inside them
(open a linked doc only when a task needs it). Keep CONTRIBUTING.md in context for the whole
session; if it drops out, re-read it.

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — system structure: the host control-plane stack
  (`commands/` → `services/` → `core/`), the Hub async shell, the `hub.thrift` IDL seam, the
  `coordinate` agent binary, the playground template.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — contribution rules: where things go, how to add a
  command / service / RPC, and the schema/migration discipline.
- **[CODESTYLE.md](CODESTYLE.md)** — how the Python is written: functions vs classes, exceptions,
  type hints, the Hub RPC code contract, output sinks.

## Running

```bash
uv sync                            # install deps + the editable package
uv run botpen db setup             # create .db/messages.db + apply migrations
uv run botpen serve                # bring the Hub container up (runs `hub serve` inside; leave running)
uv run botpen scaffold             # provision agent container(s) - interactive, or -n/--stack
uv run botpen start -n 3 --stack haiku,opus,sonnet   # db + Hub + scaffold N agents, in one shot
uv run botpen permissions list     # operator audit of the permission log
uv run botpen clean                # remove containers/images/volume/playgrounds (--db also wipes the DB)
```

`./botpen …` and `uv run botpen …` are equivalent (the shebang routes through uv). Operators use this
host CLI; inside the Hub container the command is `hub`, and agents inside their own containers use
`coordinate`.

## Git workflow

`main` is protected (GitHub branch protection):

- **Branch** off `main` as `feature/*` (also `fix/*` / `hotfix/*` / `release/*`); never commit
  straight to `main`.
- **Merge** is **rebase or squash only** - no merge commits (enforced: linear history + the merge
  button is rebase/squash). 1 PR = a linear addition on top of `main`.
- **PR titles** use conventional prefixes: `feat:` (minor), `fix:` (patch); no prefix = patch.
- **`.githooks/pre-push`** runs `ruff check --fix` and aborts the push if it changed anything or
  found an unfixable issue - review, recommit, push again. `.githooks/pre-commit` auto-formats
  staged Python. Hooks are live via `core.hooksPath=.githooks`.
- **uv only** - `uv add` / `uv sync` / `uv run`, never `pip` in committed code.
- Commit only when asked; end commit messages with the `Co-Authored-By` trailer.

## Schema & migrations (HARD constraint)

> **An AI agent MUST NOT create, edit, or delete a migration without explicit human approval.**
> Surface the need and **stop** — never write or apply a migration silently.

Full rules: ALWAYS read
[CONTRIBUTING.md § Schema & migrations](CONTRIBUTING.md#schema--migrations-hard-constraint).

## File safety

- Never commit secrets. `CLAUDE_CODE_OAUTH_TOKEN` lives in gitignored `.env.local`; the committed
  `.env` holds only defaults / placeholders.
- Don't commit generated files, the `.db/`, or `playgrounds/` contents. Update `.gitignore` when a
  change introduces new local output.

## Working style

- Keep changes focused; fix root causes over one-off patches; match existing structure and style.
- Avoid editing unrelated files. Call out any validation you could not run.
