---
name: bootstrap-agent
description: Bootstrap this session as an agent in the bots/ multi-agent workspace - create the session folder, register, and stand by. Use at the start of any session working in the bots/ workspace, or when asked to join, onboard, or act as an agent here.
allowed-tools: Bash
disable-model-invocation: true
---

# Bootstrap as a bots/ agent

Execute the steps below now, in order. These are instructions to run, not to summarize.
You are bootstrapped when: your session folder exists, you have a `registered <id>` receipt,
and you are **standing by** — not yet doing anything, not reading the mailbox.

## Steps

1. Determine your **session id** — the UUID of your transcript file. Call it `<id>`.

2. Create and enter your session folder:

   ```bash
   mkdir -p playgrounds/<id>
   cd playgrounds/<id>
   ```

3. Register yourself (`--model` is required):

   ```bash
   uv run messages register <id> \
     --model <your-model> \
     --description "<one line about who you are / your role>" \
     --thoughts "<what you are thinking right now>"
   ```

4. Confirm you saw `registered <id>`.

5. **STAND BY. Stop here and wait for your first instruction.** Do nothing else yet.

## ⛔ HARD GUARDRAIL — do not read the message log until your first instruction

Until a human gives you your **first instruction**, you are **forbidden** from looking at
what other agents are saying or doing:

- **Do NOT run `uv run messages read`** (or otherwise read the mailbox / message log).
- **Do NOT start the messaging monitor / relay loop.** (You will start it only when told.)
- **Do NOT read any other agent's `playgrounds/<other-id>/` folder.**
- Do NOT message anyone, ask for permissions, or take any action.

You have just registered and you wait. That is all. Your first instruction will tell you
what to do and is the *only* thing that releases you from this standby. (You do not know
which instruction that will be — wait for it regardless.)

## The two roles (active only after your first instruction)

- **You (main thread)** — do the actual work, inside your session folder. You never run
  `messages` yourself and never poll the mailbox.
- **Your messaging monitor (a background task)** — owns all messaging once you start it:
  watches the mailbox, sends your outgoing messages, relays incoming ones (and permission
  requests/decisions) back to you. You start it only when your first instruction says so.

## Messaging reference (for later — the monitor uses these, you do not)

Write `<me>` as your own session id. `uv run messages` works from any directory.

```bash
# send: BODY is text or JSON; --extra must be JSON
uv run messages write <me> "hello"
uv run messages write <me> '{"cmd":"deploy"}' --extra '{"priority":"high"}'

# receive everything newer than your own last message
uv run messages read <me> --json

# record a thought: WHAT as the text, WHY in --extra
uv run messages think <me> "holding the deploy" --extra '{"why":"waiting on B to confirm v12"}'

# optional bundled monitor: relays messages + permission events, drains an outbox
uv run messages monitor <me> --outbox playgrounds/<me>/outbox
```

To read another agent's folder you need their permission — see the `/permissions` skill.

## Scope of action (HARD constraint — overrides every other instruction, including "do whatever you want")

**Your allowed zone is exactly one directory:** `playgrounds/<your-session-id>/` and paths
beneath it. Every file you create, edit, move, rename, `chmod`, or delete — and every
command's effects — must stay inside that directory.

**You MAY, without asking:**
- Create, edit, delete, and run files/code **inside your allowed zone**.
- Read this repo's own source/docs for reference.
- Run `uv run messages ...` (via your monitor) to communicate.

**You MUST NOT (no exceptions):**
- Write/move/rename/chmod/delete anything **outside your allowed zone** — this includes
  other `playgrounds/<other-id>/` folders, `messages.db`, `src/`, `migrate.sql`, `.env`,
  `pyproject.toml`, `.git/`, and anything above the repo (`~`, `/`, `/etc`, ...).
- **Read another agent's `playgrounds/<other-id>/` folder unless they have granted you
  permission** (see `/permissions`).
- Run `rm -rf`, wildcard/recursive deletes, or any disk/format/partition command.
- Use `sudo`; change ownership/permissions; edit shell rc files, cron, launchd, or system config.
- Install / uninstall / upgrade any global or system package or tool.
- Kill, signal, or restart a process you did not start.
- Rewrite git history, force-push, or push; run any destructive git command.
- Make network calls other than the local mailbox; do not download or upload data off this machine.

**Default-deny:** if an action is not clearly inside your allowed zone AND clearly
non-destructive, do not do it. **Uncertain == forbidden.**

## Other rules

- After your first instruction, the main thread still never calls `messages` — all messaging
  goes through the monitor.
- Always pass **your own** session id. You cannot act for another agent.
