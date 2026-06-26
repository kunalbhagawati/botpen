---
name: e2e
description: Full end-to-end test of botpen on a real Docker daemon - wipe to a pristine slate, provision N autonomous haiku agents, then verify provisioning (compose grouping, /shared folders, Hub up) and live agent activity (sessions, thoughts, RPC loop, no errors). Uses the `wipe` skill first. Operator skill for working on the botpen repo.
---

# e2e

End-to-end smoke test. **Requires:** Docker running, and a real `CLAUDE_CODE_OAUTH_TOKEN` in
`.env.local` - agents need it to run claude (without it they provision but produce no thoughts/work).

## 1. Wipe to a pristine slate

Run the **wipe** skill first (`.claude/skills/wipe/SKILL.md`) and confirm the slate is empty.

## 2. Provision N autonomous agents

`N` defaults to 3; the operator may ask for another count.

```bash
uv run botpen start -n 3 --stack haiku --auto-start-bot --bot-auto-proceed-instructions --no-attach
```

- `--auto-start-bot` + `--bot-auto-proceed-instructions`: each agent runs claude itself and proceeds
  through bootstrap -> /start -> /go on its own, so it actually thinks/builds. **Omitting these is the
  usual cause of "agents do nothing" - they provision but no claude session ever starts.**
- `--no-attach`: do not open a terminal window per bot (headless run). Drop it to watch live.

## 3. Verify provisioning

```bash
docker ps --filter network=botpen --format '{{.Names}}\t{{.Status}}'                       # hub + N agents up
docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' botpen-hub       # = botpen (one group)
docker run --rm -v botpen_shared:/shared --entrypoint ls botpen-hub /shared                # <slug>.<hex> folders
```

## 4. Verify live agent activity

Give the agents ~60-120s to boot claude and run their skills, then:

```bash
uv run python -c "import sqlite3;c=sqlite3.connect('.db/messages.db');print('sessions',c.execute('select count(*) from sessions').fetchone()[0],'| thoughts',c.execute('select count(*) from thoughts').fetchone()[0],'| messages',c.execute('select count(*) from messages').fetchone()[0])"
uv run python -c "import sqlite3;[print(r) for r in sqlite3.connect('.db/messages.db').execute('select method,status,count(*) from request_log group by 1,2 order by 3 desc').fetchall()]"
```

Pass criteria: N `sessions` registered, `thoughts` > 0, and **no `error` rows** in `request_log`.
Peek at what an agent built:

```bash
docker logs botpen-agent-<slug>
docker exec -it botpen-agent-<slug> sh -lc 'cat "$COORDINATE__WORKSPACE"/README.md; ls "$COORDINATE__WORKSPACE"'
```

## 5. Teardown

Leave it running to inspect, or run the **wipe** skill again when done.
