#!/usr/bin/env bash
# The API on Render's free plan. Nothing on its disk survives a restart, so the message and signing keys
# arrive as one base64 tarball in VERYTAS_KEYS_TGZ and are unpacked before the API starts. They must be
# the keys the data in Neon was sealed and signed with (deploy/render/README.md), or every message reads
# as unreadable and every finding's signature fails.
set -euo pipefail
KEYS="${VERYTAS_KEYS_DIR:-/tmp/verytas-keys}"
if [ -n "${VERYTAS_KEYS_TGZ:-}" ]; then
  mkdir -p "$KEYS"
  chmod 700 "$KEYS"
  if ! printf '%s' "$VERYTAS_KEYS_TGZ" | base64 -d | tar -xz -C "$KEYS"; then
    echo "VERYTAS_KEYS_TGZ is not a base64 tar.gz of the keys folder" >&2
    exit 1
  fi
fi
unset VERYTAS_KEYS_TGZ
# Without every one of them the API would mint new keys on first use and quietly orphan what is stored:
# messages that no longer open, findings whose signatures no longer verify. The files sit at the top level.
for f in messages.key assets-worker.pem claims-worker.pem crosscheck-worker.pem deterministic-worker.pem \
         intake-worker.pem media-worker.pem presentation-worker.pem semantic-worker.pem; do
  if [ ! -s "$KEYS/$f" ]; then
    echo "missing $f in $KEYS: set VERYTAS_KEYS_TGZ to the keys the database was seeded with" >&2
    exit 1
  fi
done
export VERYTAS_KEYS_DIR="$KEYS"
export VERYTAS_MEMORY_DIR="${VERYTAS_MEMORY_DIR:-/tmp/verytas-memory}"
# One worker: background reviews, the live message hub and the request pacer all live in this process.
# No proxy headers: only the web app's server calls the API, so a forwarded address would be either
# Vercel's or one a caller made up.
exec uvicorn verytas.main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 --no-proxy-headers
