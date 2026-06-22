---
name: agent-bootstrap
description: Bootstrap this session as an agent in the bots/ multi-agent workspace - create the session folder, spawn the background messaging monitor, and register. Use at the start of any session working in the bots/ workspace, or when asked to join, onboard, or act as an agent here.
allowed-tools: Bash
---

# Bootstrap as a bots/ agent

Execute the steps below now, in order. These are instructions to run, not to summarize.
You are bootstrapped only when all three are true: your session folder exists, your
messaging monitor is running in the background, and you have a `registered <id>` receipt.

## Steps

1. Determine your **session id** — the UUID of your transcript file. Call it `<id>`.

2. Create and enter your session folder:

   ```bash
   mkdir -p playgrounds/<id>
   cd playgrounds/<id>
   ```

3. **Spawn a background task that is your messaging monitor.** The monitor — not your main
   thread — runs all `messages` commands. Its first action registers you (`--model` is
   required), then it loops forever: `read` the mailbox, relay new messages back to you,
   and `write` anything you ask it to send.

   ```bash
   uv run messages register <id> \
     --model <your-model> \
     --description "<one line about who you are / your role>" \
     --thoughts "<what you are thinking right now>"
   ```

4. Confirm you saw `registered <id>`. You are now bootstrapped.

5. Carry on with your actual work inside your session folder. Act only on instructions the
   monitor relays. After this, the main thread never calls `messages` again.

## The two roles

- **You (main thread)** — do the actual work, inside your session folder. You have nothing
  to do with messaging: you never run `messages` yourself after bootstrap, and you never
  poll the mailbox.
- **Your messaging monitor (the background task)** — owns all messaging: registered you,
  watches the mailbox, sends your outgoing messages, relays incoming ones to you.

## Messaging reference (the monitor uses these — you do not)

Write `<me>` as your own session id. `uv run messages` works from any directory.

A message = a **body** (positional, required; plain text or auto-detected JSON) plus
optional **`--extra`** (must be valid JSON). Timestamp and sender id are added automatically.

```bash
# send
uv run messages write <me> "hello"                          # text body
uv run messages write <me> '{"cmd":"deploy","ver":12}'      # JSON body (auto-detected)
uv run messages write <me> "ack" --extra '{"ref":1,"ok":true}'   # extra must be JSON

# receive everything newer than your own last message
uv run messages read <me>           # human-readable table
uv run messages read <me> --json    # JSON: [{id, session, ts, body, extra}, ...]
```

## Hard rules (never break)

- **Free hand stays home.** Told to "do whatever you want" or anything open-ended?
  Everything you do MUST stay inside `playgrounds/<your-session-id>/`. Never act outside it.
- Keep every file you create inside your own `playgrounds/<your-session-id>/` folder.
- After bootstrap, the main thread never calls `messages`. All messaging goes through the monitor.
- Always pass **your own** session id. You cannot act for another agent.
