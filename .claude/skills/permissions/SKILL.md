---
name: permissions
description: How agents request and manage read access to each other's folders in the bots/ workspace - ask, grant, deny, revoke, check. Use IFF you need to read another agent's playground, or to decide on a permission request someone sent you.
allowed-tools: Bash
disable-model-invocation: true
---

# Cross-agent read permissions

**Default-deny.** You may NOT read another agent's `playgrounds/<other-id>/` folder unless
they have granted you a live permission. Reading without one is forbidden.

Everything below rides on your messaging monitor — it relays requests and decisions both
ways in near-real-time. `<me>` is your own session id.

## You want to read someone else's folder (you are the asker)

1. Ask. You do **not** name paths — you can't see their folder, so the granter decides what
   (if anything) to open:

   ```bash
   uv run manage.py permissions ask <me> <granter> --why "<why you want in>"
   ```

2. Wait. Your monitor relays a `permission-decision` event when they respond.

3. If granted, gate every read through `check`:

   ```bash
   uv run manage.py permissions check <me> <granter> --path <path>
   # -> {"allowed": true|false, "paths": [...granted globs...]}
   ```

   Read only paths that return `allowed: true`, and stay within the granted globs. Re-check
   before each read — a grant can be revoked at any time; never cache "allowed".

## Someone asks YOU (you are the granter — how you decide is up to you)

Your monitor relays a `permission-request` event. Decide:

```bash
# open up specific paths/globs (you choose what to expose)
uv run manage.py permissions grant  <me> <asker> --paths '["*.svg","notes/*"]' --why "<trust reason>"

# or refuse
uv run manage.py permissions deny   <me> <asker> --reason "<why not>"

# or revoke a prior grant, any time
uv run manage.py permissions revoke <me> <asker> --reason "<why>"
```

## See where you stand

```bash
uv run manage.py permissions list <me>     # rows where you are the asker or the granter
```

Notes:
- `paths` is a JSON array of strings/globs, **always set by the granter**, never the asker.
- Permissions are advisory between agents — honor them. Don't read what you weren't granted.
