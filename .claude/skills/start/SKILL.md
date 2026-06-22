---
name: start
description: Turn a bootstrapped agent loose in its sandbox - do whatever you want, no asking, nothing destructive - and log a what/why thought trail. Invoke with /start once an agent has bootstrapped.
disable-model-invocation: true
---

# Start — go free (in your sandbox)

Now, do whatever you want.

- Do not ask me.
- Do not run destructive commands.
- Just do what you want **without fucking up my machine (hard constraint).**

Your hard boundary is exactly the one from bootstrap: everything you do stays **inside your
own session folder** `playgrounds/<your-session-id>/`. Nothing outside it, nothing
destructive, nothing system-level; when unsure, don't (default-deny). The full scope rules
live in the `bootstrap-agent` skill. If you have not bootstrapped yet, run
`/bootstrap-agent` first.

## Log a what/why thought trail

As you go — whenever you start something, decide something, or your intent changes — have
your **monitor** (never the main thread) append a thought. The **what** is the thought text;
the **why** rides in `--extra` as `{"why": ...}`, so the thoughts column holds only the what:

```bash
uv run messages think <your-session-id> "<what you want to do right now, at this moment>" --extra '{"why":"<why>"}'
```

Do it often enough to leave a readable trail of what you did and why. Never block on it.
