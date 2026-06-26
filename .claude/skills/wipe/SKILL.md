---
name: wipe
description: Wipe all botpen state to a pristine slate - every botpen container, image, volume, network, and playground folder, the SQLite DB, and the .tmp scratch dir. Use before an e2e run, or to fully reset a dev machine. Operator skill for working on the botpen repo (not a container skill).
---

# wipe

Reset botpen to a pristine slate. Removes **everything** botpen created locally.

Run from the repo root:

```bash
uv run botpen clean --folders --docker --db --yes   # containers + images + volumes + networks + playgrounds + DB
rm -rf .tmp                                          # scratch (logs, monitor cursor state)
```

> Note: `botpen clean --db` *alone* removes only the DB - passing `--db` suppresses the no-flag
> default of `--folders --docker`. The explicit `--folders --docker --db` above does the full wipe.

Then confirm pristine (every line should print nothing / "No such file"):

```bash
docker ps -a --filter name=botpen- --format '{{.Names}}'
docker images --filter reference='botpen-*' --format '{{.Repository}}'
docker volume ls -q --filter name=botpen
docker network ls --filter name=botpen --format '{{.Name}}'
ls .db .tmp 2>&1
```

If anything remains (e.g. a wedged container), force it:

```bash
docker rm -f $(docker ps -aq --filter name=botpen-) 2>/dev/null || true
```
