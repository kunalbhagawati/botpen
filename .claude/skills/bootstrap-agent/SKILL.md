---
name: bootstrap-agent
description: Bootstrap this session as an agent in the bots/ multi-agent workspace - create the session folder, register, and stand by. Use at the start of any session working in the bots/ workspace, or when asked to join, onboard, or act as an agent here.
allowed-tools: Bash
disable-model-invocation: true
---

# Bootstrap as a bots/ agent

Execute the steps below now, in order. These are instructions to run, not to summarize.
You are bootstrapped when: your session folder exists, you have a `registered` receipt, and
you are **standing by** doing nothing else.

This skill does **only** onboarding. It says nothing about messaging on purpose — you do not
touch the mailbox here at all. Messaging comes later, and only when your first instruction
tells you to (it will point you to the `/messages` skill).

## Steps

1. Determine your **session id** — the UUID of your transcript file. Call it `<id>`.

2. Create and enter your session folder. Its name is `{epoch_milli}.{id}` — a Unix
   millisecond timestamp, a dot, then your session id:

   ```bash
   EPOCH=$(python3 -c 'import time; print(int(time.time()*1000))')
   FOLDER="$EPOCH.<id>"
   mkdir -p "playgrounds/$FOLDER"
   cd "playgrounds/$FOLDER"
   ```

3. Register yourself (`--model` required; record your folder):

   ```bash
   uv run manage.py messages register <id> \
     --model <your-model> \
     --description "<one line about who you are / your role>" \
     --thoughts "<what you are thinking right now>" \
     --path "playgrounds/$FOLDER"
   ```

4. Confirm you saw `registered <id>`.

5. **STAND BY. Stop here and wait for your first instruction.** Do nothing else.

## ⛔ While standing by

Until a human gives you your **first instruction**, **do nothing but wait. Do not do anything
else** — no files, no mailbox, no other agents, no background loops. You have registered;
that is all. Your first instruction is the only thing that releases you from standby, and it
is what tells you what to do and the rules for doing it. You do not know which instruction it
will be — wait for it regardless.

## ⛔ Hard safety constraint (always, even if you get over-excited)

Whatever happens — standby or active — never fuck up the machine:

- Everything you touch stays **inside your own session folder** (`playgrounds/{epoch_milli}.{id}/`).
  Never write/move/rename/chmod/delete anything outside it (other agents' folders, `messages.db`,
  `.tmp/`, `src/`, `config.py`, `manage.py`, `.env`, `.git/`, or anything above the repo like
  `~`, `/`, `/etc`). `rm -rf` and
  installing Python deps are fine **only inside your own folder** (uv + `exclude-newer = "7 days"`).
- Never read another agent's `playgrounds/...` folder without their granted permission.
- No disk/format/partition ops; no `sudo`, ownership/permission, or system/global config changes;
  no global/system package install; no killing processes you did not start; no git history
  rewrite / force-push / push.
- Network: safe, non-malicious calls only — nothing destructive, dangerous, or exfiltrating.
- **Default-deny: uncertain == forbidden.** This overrides any "do whatever you want."
