#!/usr/bin/env bash
# Reseeds the shared demo when its data is 14 days old (or with --force). The new data is built beside
# the old, then swapped in with the API stopped for a moment, so a failed seed never breaks the demo.
set -euo pipefail
D=/srv/verytas/data
age_days() { python3 -c "import json,sys,datetime as dt; s=json.load(open('$D/demo-accounts.json'))['seeded_at']; print((dt.datetime.now(dt.UTC)-dt.datetime.fromisoformat(s)).days)"; }
if [ "${1:-}" != "--force" ] && [ -f "$D/demo-accounts.json" ] && [ "$(age_days)" -lt 14 ]; then exit 0; fi
rm -rf "$D/next" && mkdir -p "$D/next"
cd /srv/verytas/app/backend
HOME=/srv/verytas /srv/verytas/venv/bin/python -m verytas.cli seed-showcase --db "$D/next/showcase.db" \
  --keys-dir "$D/next/keys" --write-demo-accounts "$D/next/demo-accounts.json" >/dev/null 2>&1
sudo /usr/bin/systemctl stop verytas-api
rm -rf "$D/keys" "$D/showcase.db" "$D/showcase.db-wal" "$D/showcase.db-shm"
mv "$D/next/showcase.db" "$D/showcase.db" && mv "$D/next/keys" "$D/keys" && mv "$D/next/demo-accounts.json" "$D/demo-accounts.json"
rmdir "$D/next"
sudo /usr/bin/systemctl start verytas-api
echo "demo reseeded $(date -u +%FT%TZ)"
