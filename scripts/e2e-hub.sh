#!/usr/bin/env bash
# End-to-end check for the containerized Hub. Run from the repo root: scripts/e2e-hub.sh
#
# Brings up the Hub container, spawns 2 agents via `playground` (which execs into the Hub), and
# verifies they registered through hub:8787 and their relays connected through hub:8788. Leaves
# everything running for inspection; clean up with: ./manage.py teardown --db --yes
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== clean slate ==="
./manage.py teardown --db --yes || true

echo "=== bring up the Hub container (first build ~1 min) ==="
./manage.py serve

echo "=== spawn 2 agents (haiku, opus) - playground execs into the Hub ==="
uv run playground start -n 2 -c "haiku,opus"

echo "=== wait for agents to bootstrap ==="
sleep 90

echo "=== Hub container + agents on the botpen network ==="
docker ps --filter network=botpen --format '{{.Names}}\t{{.Status}}'

echo "=== sessions registered (DB lives on the Hub-only volume) ==="
docker exec botpen-hub /app/.venv/bin/python -c \
  "import sqlite3; c=sqlite3.connect('/data/messages.db'); print(c.execute('select c.scaffold_slug, s.model from sessions s join scaffolds c on s.scaffold_id=c.scaffold_id').fetchall())"

echo "=== relays connected via hub:8788 (expect relay-up, NOT 4001 invalid token) ==="
for a in $(docker ps --filter network=botpen --filter name=botpen-agent --format '{{.Names}}'); do
  printf '%s: ' "$a"
  docker exec "$a" sh -lc 'tail -1 "$COORDINATE__WORKSPACE/.relay.jsonl"' 2>/dev/null || echo "(no relay log yet)"
done

echo "=== done - inspect above. teardown with: ./manage.py teardown --db --yes ==="
