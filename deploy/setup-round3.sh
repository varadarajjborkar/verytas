#!/usr/bin/env bash
# One-time server setup for the Round 3 additions, run as the ubuntu user on the API server:
#
#   ssh -i ~/.ssh/verytas-deploy.pem ubuntu@<server> 'bash -s' < deploy/setup-round3.sh
#
# 1. Redis for conversations: loopback only, no persistence (the database is the record, Redis only fans
#    events out and caches pages), 64 MB with old cache pages evicted first. The API finds it through
#    VERYTAS_REDIS_URL in api.env; without it, conversations still work in one process.
# 2. The keep-warm timer for the vision worker (deploy/systemd/verytas-keepwarm.*). Its dates, hours and
#    10 USD cap are in the unit file; before 31 Oct it does nothing.
#
# Safe to run twice: every step checks before it changes anything.
set -euo pipefail

REPO=/srv/verytas/repo.git
ENV=/srv/verytas/etc/api.env

if ! command -v redis-server >/dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq redis-server
fi
conf=/etc/redis/redis.conf
sudo sed -i -E 's/^bind .*/bind 127.0.0.1 -::1/; s/^protected-mode .*/protected-mode yes/; s/^appendonly .*/appendonly no/' "$conf"
# redis.conf is readable by root only, so the "already there?" checks need sudo too.
sudo grep -q '^maxmemory 64mb' "$conf" || echo 'maxmemory 64mb' | sudo tee -a "$conf" >/dev/null
sudo grep -q '^maxmemory-policy allkeys-lru' "$conf" || echo 'maxmemory-policy allkeys-lru' | sudo tee -a "$conf" >/dev/null
sudo grep -q '^save ""' "$conf" || echo 'save ""' | sudo tee -a "$conf" >/dev/null
sudo systemctl enable --now redis-server >/dev/null
sudo systemctl restart redis-server
[ "$(redis-cli ping)" = "PONG" ] || { echo "redis did not answer" >&2; exit 1; }

if ! sudo grep -q '^VERYTAS_REDIS_URL=' "$ENV"; then
  echo 'VERYTAS_REDIS_URL=redis://127.0.0.1:6379/0' | sudo tee -a "$ENV" >/dev/null
fi

# A release holds only backend/ and web/; the unit files come from the deployed commit in the server's clone.
for unit in verytas-keepwarm.service verytas-keepwarm.timer; do
  sudo -u verytas git -C "$REPO" show "live:deploy/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
  sudo chmod 0644 "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable --now verytas-keepwarm.timer >/dev/null
sudo systemctl restart verytas-api

echo "redis: $(redis-cli config get maxmemory | tail -1) bytes, bind $(redis-cli config get bind | tail -1)"
systemctl list-timers verytas-keepwarm.timer --no-pager | sed -n 2p
