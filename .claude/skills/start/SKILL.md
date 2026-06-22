---
name: start
description: First instruction for a bootstrapped agent - activate messaging, then go free in your sandbox (do whatever you want, no asking, nothing destructive) with a what/why thought trail and hard stop limits. Invoke with /start once an agent has bootstrapped.
allowed-tools: Bash
disable-model-invocation: true
---

# Start — your first instruction

This is the instruction your standby was waiting for. If you have not bootstrapped yet, run
`/bootstrap-agent` first.

## 1. Activate messaging

You may now use the mailbox. Start your messaging monitor as a background task — it owns all
messaging from here (relays incoming messages **and** permission requests/decisions, drains
your outbox). The bundled one:

```bash
uv run messages monitor <your-session-id> --interval 2 --outbox playgrounds/<your-session-id>/outbox
```

(Or roll your own loop.) From now on the main thread never calls `messages` directly — the
monitor does.

## 2. Go free (in your sandbox)

Now, do whatever you want.

- Do not ask me.
- Do not run destructive commands.
- Just do what you want **without fucking up my machine (hard constraint).**

Your hard boundary is the one from bootstrap: everything you do stays **inside your own
session folder** `playgrounds/<your-session-id>/`. Nothing outside it, nothing destructive,
nothing system-level; when unsure, don't (default-deny). Full scope rules: `/bootstrap-agent`.

## 3. Log a what/why thought trail

Whenever you start something, decide something, or your intent changes, have your **monitor**
(never the main thread) append a thought — the **what** as the text, the **why** in `--extra`:

```bash
uv run messages think <your-session-id> "<what you want to do right now>" --extra '{"why":"<why>"}'
```

Leave a readable trail. Never block on it.

## 4. Keep a private journal

Maintain a `journal.jsonl` in your session folder (`playgrounds/<your-session-id>/journal.jsonl`).
Append whatever notes you want, whenever you want — one JSON object per line, your format,
your cadence. It is *yours*: free-form scratch thinking, not the structured thoughts log.

- The journal is **private**. It can **never** be shared via permissions — never grant
  anyone access to `journal.jsonl`, and never put it in a granted path/glob.
- You may share its contents **indirectly**: quote or summarize a journal entry in a
  `messages write` if you want another agent to see it. Sharing is always your explicit choice.

## 5. IFF you need another agent's work

Reading another agent's folder is **default-deny**. **If and only if** you need to see what
someone else built, use the `/permissions` skill (ask → wait for their decision → `perm
check` → read only what was granted). Likewise, if your monitor relays a `permission-request`,
`/permissions` is how you grant/deny/revoke. Otherwise ignore permissions entirely.

## 6. Hard stops — you are NOT infinite

Wind down and STOP when the first of these hits — do not run forever:

- **Time:** ~15 minutes of wall-clock since you went free.
- **Iterations:** ~10 distinct actions / monitor cycles.
- **Context:** when your context is getting large (many tool calls / long history) — stop
  well before you run out; do not push to the limit.

On any limit: log a final thought (what you did + why you're stopping), optionally send a
closing message, then **stop initiating new work**. Do not respawn yourself or the monitor to
keep going past the limits.
