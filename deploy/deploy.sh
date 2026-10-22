#!/usr/bin/env bash
# Ships the committed tree to the demo server, rebuilds the web app there and restarts both services.
# Usage: deploy/deploy.sh [user@host]   (SSH key: ~/.ssh/verytas-deploy.pem)
# Only committed files travel (git archive), so a half-edited working tree never reaches the server.
set -euo pipefail
HOST=${1:-ubuntu@15.252.228.168}
KEY=${VERYTAS_SSH_KEY:-$HOME/.ssh/verytas-deploy.pem}
cd "$(git rev-parse --show-toplevel)"
ssh_() { ssh -i "$KEY" "$HOST" "$@"; }

git archive --format=tar HEAD backend web | ssh_ 'sudo tar -x -C /srv/verytas/app && sudo chown -R verytas:verytas /srv/verytas/app'
git rev-parse --short HEAD | ssh_ 'sudo -u verytas tee /srv/verytas/app/REVISION >/dev/null'
ssh_ 'sudo -u verytas bash -s' <<'REMOTE'
set -euo pipefail
cd /srv/verytas
venv/bin/pip install -q ./app/backend
cd app/web
export HOME=/srv/verytas NEXT_TELEMETRY_DISABLED=1 CI=1
corepack pnpm install --frozen-lockfile --silent
corepack pnpm build > /srv/verytas/build.log 2>&1 || { tail -30 /srv/verytas/build.log; exit 1; }
REMOTE
ssh_ 'sudo systemctl restart verytas-api verytas-web && sleep 4 && systemctl is-active verytas-api verytas-web'
echo "deployed $(git rev-parse --short HEAD)"
