#!/usr/bin/env bash
# End-to-end check for the containerized Hub. Run from the repo root: scripts/e2e-hub.sh
#
# Brings up the Hub container, provisions 2 agents host-side via `botpen start`, and verifies they
# registered through hub:8787 and their relays connected through hub:8788. Leaves everything running
# for inspection; clean up with: ./botpen clean --db --yes
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== clean slate ==="
./botpen clean --db --yes || true

echo "=== provision 2 agents (haiku, opus); start sets up the DB + brings the Hub up ==="
./botpen start -n 2 --stack "haiku,opus" --no-attach

echo "=== wait for agents to bootstrap ==="
sleep 90

echo "=== Hub container + agents on the botpen network ==="
docker ps --filter network=botpen --format '{{.Names}}\t{{.Status}}'

echo "=== sessions registered (DB at .db/messages.db, bind-mounted into the Hub at /data) ==="
docker exec botpen-hub /app/.venv/bin/python -c \
  "import sqlite3; c=sqlite3.connect('/data/messages.db'); print(c.execute('select c.scaffold_slug, s.model from sessions s join scaffolds c on s.scaffold_id=c.scaffold_id').fetchall())"

echo "=== relays connected via hub:8788 (expect relay-up, NOT 4001 invalid token) ==="
for a in $(docker ps --filter network=botpen --filter name=botpen-agent --format '{{.Names}}'); do
  printf '%s: ' "$a"
  docker exec "$a" sh -lc 'tail -1 "$COORDINATE__WORKSPACE/.relay.jsonl"' 2>/dev/null || echo "(no relay log yet)"
done

echo "=== done - inspect above. clean up with: ./botpen clean --db --yes ==="
