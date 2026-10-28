#!/usr/bin/env bash
# Reseeds the shared demo when its data is 14 days old (or with --force). The new data is built beside
# the old, then swapped in with the API stopped for a moment, so a failed seed never breaks the demo.
set -euo pipefail
D=/srv/verytas/data
age_days() { python3 -c "import json,sys,datetime as dt; s=json.load(open('$D/demo-accounts.json'))['seeded_at']; print((dt.datetime.now(dt.UTC)-dt.datetime.fromisoformat(s)).days)"; }
if [ "${1:-}" != "--force" ] && [ -f "$D/demo-accounts.json" ] && [ "$(age_days)" -lt 14 ]; then exit 0; fi
# After a failed seed the daily timer would start another long one on the shared box every day; wait three
# days between tries unless forced.
if [ "${1:-}" != "--force" ] && [ -n "$(find "$D" -maxdepth 1 -name reset-failed -mtime -3 2>/dev/null)" ]; then
  exit 0
fi
rm -rf "$D/next" && mkdir -p "$D/next"
cd /srv/verytas/app/backend
# Every company with every piece takes tens of minutes on the 2 vCPU box. The seed prints a line per
# company to the log, the timeout stops a stuck seed before it holds the box for good (the live demo is
# untouched until the swap below), and SEED_PIECES caps pieces per company for a faster reset.
LOG="$D/reset-demo.log"
extra=()
[ -n "${SEED_PIECES:-}" ] && extra+=(--pieces "$SEED_PIECES")
echo "seed started $(date -u +%FT%TZ)" >>"$LOG"
if ! HOME=/srv/verytas timeout "${SEED_TIMEOUT:-90m}" /srv/verytas/venv/bin/python -m verytas.cli seed-showcase \
    --db "$D/next/showcase.db" --keys-dir "$D/next/keys" --write-demo-accounts "$D/next/demo-accounts.json" \
    ${extra[@]+"${extra[@]}"} >>"$LOG" 2>&1; then
  echo "seed failed or timed out; the current demo is unchanged (see $LOG)" >&2
  rm -rf "$D/next"
  touch "$D/reset-failed"
  exit 1
fi
sudo /usr/bin/systemctl stop verytas-api
rm -rf "$D/keys" "$D/showcase.db" "$D/showcase.db-wal" "$D/showcase.db-shm"
# What Inki kept about people is keyed by their ids, which the new data hands out again: it goes with the old
# data, or one demo person would inherit another's. The embedding model in memory/models stays.
rm -rf "$D/memory/personal"
mv "$D/next/showcase.db" "$D/showcase.db" && mv "$D/next/keys" "$D/keys" && mv "$D/next/demo-accounts.json" "$D/demo-accounts.json"
rmdir "$D/next"
rm -f "$D/reset-failed"
sudo /usr/bin/systemctl start verytas-api
echo "demo reseeded $(date -u +%FT%TZ)"
