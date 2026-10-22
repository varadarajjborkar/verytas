#!/usr/bin/env bash
# Deploys now instead of waiting for the server's timer: the server pulls origin/main and runs
# autodeploy.sh. Push to main first; only what is on GitHub's main can reach production.
# Usage: deploy/deploy.sh [--force]   (SSH key: ~/.ssh/verytas-deploy.pem; host override: VERYTAS_HOST)
set -euo pipefail
HOST=${VERYTAS_HOST:-ubuntu@15.252.228.168}
KEY=${VERYTAS_SSH_KEY:-$HOME/.ssh/verytas-deploy.pem}
ssh -i "$KEY" "$HOST" "sudo -u verytas /srv/verytas/bin/autodeploy.sh ${1:-} && cat /srv/verytas/app/REVISION"
