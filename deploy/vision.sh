#!/usr/bin/env bash
# The vision worker instance (verytas/vision): cloud-init user data, then the boot-time updater. It holds
# nothing that isn't on GitHub. Each boot fetches `live` (the branch the API server follows), installs the
# hash-pinned vision lock when it changed, warms the models, and runs the worker. It stops itself after 20
# idle minutes; the API starts it again on demand (verytas/vision/wake.py).
#
# Cost safety comes first. The stop timer is installed before anything that can fail, and it reads idleness
# from a file the worker touches on every request, not from the worker answering: a worker that never
# starts, or crashes, still gets its instance stopped (30 minutes after boot at the latest).
#
# Secrets come from SSM Parameter Store through the instance role, never from user data:
#   /verytas/vision/token       the token the API sends (X-Vision-Token)
#   /verytas/vision/deploy_key  a read-only GitHub deploy key for this repository
#
# Code and venv belong to root and are read-only to the worker, which writes only its models, cache and
# state. A push to `live` runs here as root at the next boot, as it does on the API server.
#
# Launch with --instance-initiated-shutdown-behavior stop, so `shutdown` stops rather than terminates.
set -euo pipefail
ROOT=/srv/vision
REPO_URL=git@github.com:varadarajjborkar/verytas.git
BRANCH=live
SAM2="git+https://github.com/facebookresearch/sam2@2b90b9f5ceec907a1c18123530e92e794ad901a4"
# GitHub's published ed25519 host key (docs.github.com, "GitHub's SSH key fingerprints"): pinned, not
# trusted on first use.
GITHUB_KEY="github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
BOOT=/usr/local/sbin/verytas-vision-boot
log() { echo "$(date -u +%FT%TZ) vision: $*"; }

safety_net() {
  # Written from this script itself, first, on every run: whatever fails after this, the instance stops.
  mkdir -p "$ROOT/state"
  cat > /usr/local/sbin/verytas-vision-idle <<'EOF'
#!/bin/sh
# Stop the instance when the worker has had no request for 20 minutes, or never had one in 30 since boot.
up=$(cut -d. -f1 /proc/uptime)
last=/srv/vision/state/last_used
if [ -f "$last" ]; then
  idle=$(( $(date +%s) - $(stat -c %Y "$last") ))
  [ "$up" -gt 900 ] && [ "$idle" -gt 1200 ] && exec shutdown -h now "vision worker idle"
else
  [ "$up" -gt 1800 ] && exec shutdown -h now "vision worker never used"
fi
exit 0
EOF
  chmod 755 /usr/local/sbin/verytas-vision-idle
  cat > /etc/systemd/system/verytas-vision-idle.service <<'EOF'
[Unit]
Description=Stop the vision instance when idle
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/verytas-vision-idle
EOF
  cat > /etc/systemd/system/verytas-vision-idle.timer <<'EOF'
[Unit]
Description=Check the vision worker for idleness
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable -q --now verytas-vision-idle.timer
}

install_once() {
  [ -f "$ROOT/.installed" ] && return
  log "first boot: packages and user"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q && apt-get install -yq python3.12-venv git curl
  snap list aws-cli >/dev/null 2>&1 || snap install aws-cli --classic
  id vision >/dev/null 2>&1 || useradd --system --home "$ROOT" --shell /usr/sbin/nologin vision
  mkdir -p "$ROOT"/{etc,models,cache,state}
  chown vision:vision "$ROOT"/{models,cache,state}
  echo "$GITHUB_KEY" > "$ROOT/etc/github_known_hosts"
  touch "$ROOT/.installed"  # last: a failure above is retried on the next boot
}

secrets() {
  local imds region token
  imds=$(curl -sf -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
  region=$(curl -sf -H "X-aws-ec2-metadata-token: $imds" http://169.254.169.254/latest/meta-data/placement/region)
  umask 077
  aws ssm get-parameter --region "$region" --with-decryption --name /verytas/vision/deploy_key \
    --query Parameter.Value --output text > "$ROOT/etc/deploy_key.new"
  mv "$ROOT/etc/deploy_key.new" "$ROOT/etc/deploy_key"  # root only: the worker never needs it
  token=$(aws ssm get-parameter --region "$region" --with-decryption --name /verytas/vision/token \
    --query Parameter.Value --output text)
  [ -n "$token" ] || { log "empty token from SSM"; exit 1; }
  printf 'VERYTAS_VISION_TOKEN=%s\nVERYTAS_VISION_MODELS_DIR=%s/models\nVERYTAS_VISION_STATE=%s/state\nHF_HOME=%s/cache\n' \
    "$token" "$ROOT" "$ROOT" "$ROOT" > "$ROOT/etc/worker.env"
  chown root:vision "$ROOT/etc/worker.env" && chmod 640 "$ROOT/etc/worker.env"
}

update() {
  export GIT_SSH_COMMAND="ssh -i $ROOT/etc/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=$ROOT/etc/github_known_hosts -o StrictHostKeyChecking=yes"
  if [ ! -d "$ROOT/app/.git" ]; then
    rm -rf "$ROOT/app"
    git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$ROOT/app"
  else
    git -C "$ROOT/app" fetch -q --depth 1 origin "$BRANCH" && git -C "$ROOT/app" reset -q --hard FETCH_HEAD
  fi
  local lock="$ROOT/app/backend/requirements-vision.lock" stamp="$ROOT/venv/.lock.sha256"
  if [ ! -f "$stamp" ] || ! sha256sum --status -c "$stamp" 2>/dev/null; then
    log "installing the vision lock"
    rm -rf "$ROOT/venv"
    python3.12 -m venv "$ROOT/venv"
    "$ROOT/venv/bin/pip" install -q --require-hashes -r "$lock"
    # Not on PyPI: installed from its pinned commit, built against the locked torch and setuptools.
    SAM2_BUILD_CUDA=0 "$ROOT/venv/bin/pip" install -q --no-deps --no-build-isolation "$SAM2"
    # Models are fetched now, not when the worker first loads them: a download would outlast a wake.
    log "fetching the models"
    (cd "$ROOT/app/backend" && set -a && . "$ROOT/etc/worker.env" && set +a && \
      runuser -u vision -- "$ROOT/venv/bin/python" -c \
      "from pathlib import Path; from verytas.vision.chain import Chain; Chain(Path('$ROOT/models'))")
    sha256sum "$lock" > "$stamp"  # last: a half-finished install is redone from scratch next boot
  fi
  # The next boot runs the script this commit carries; the one running now is never rewritten under it.
  install -m 755 "$ROOT/app/deploy/vision.sh" "$BOOT.new" && mv "$BOOT.new" "$BOOT"
}

units() {
  cat > /etc/systemd/system/verytas-vision.service <<EOF
[Unit]
Description=Verytas vision worker
After=verytas-vision-update.service
Requires=verytas-vision-update.service
[Service]
User=vision
WorkingDirectory=$ROOT/app/backend
EnvironmentFile=$ROOT/etc/worker.env
ExecStart=$ROOT/venv/bin/python -m verytas.vision.worker --port 8100
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$ROOT/models $ROOT/cache $ROOT/state
InaccessiblePaths=$ROOT/etc/deploy_key
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
EOF
  # The worker starts only after a successful update: never on stale or half-installed code.
  cat > /etc/systemd/system/verytas-vision-update.service <<EOF
[Unit]
Description=Fetch live and update the vision worker
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=40min
ExecStart=$BOOT --boot
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable -q verytas-vision-update.service verytas-vision.service
}

safety_net
units
if [ "${1:-}" = "--boot" ]; then
  install_once
  secrets
  update
else
  # First boot (cloud-init): install this script as the boot updater and let systemd run it, so first boot
  # and every later boot take the same path, with the worker started only after it succeeds.
  install -m 755 "$0" "$BOOT"
  systemctl start --no-block verytas-vision.service
fi
log "boot step done"
