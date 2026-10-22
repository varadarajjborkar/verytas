#!/usr/bin/env bash
# Pull-based deploys. main is production, but the server follows `live`, which CI moves to a main commit
# only after every check passes. A timer runs this every few minutes as the verytas user; when `live`
# has moved, it builds the new commit in its own release folder, switches the app symlink,
# restarts, and rolls back if the new release doesn't answer its health checks.
#
# Pulling (rather than GitHub pushing over SSH) keeps port 22 closed to everyone but the team, and the
# server only ever holds a read-only deploy key.
#
# Usage: autodeploy.sh [--force]   (--force rebuilds `live` even if it is already deployed, or failed before)
set -euo pipefail
ROOT=/srv/verytas
REPO=$ROOT/repo.git
REL=$ROOT/releases
KEEP=3
BRANCH=live

exec 9>"$ROOT/.autodeploy.lock"
flock -n 9 || exit 0

export HOME=$ROOT NEXT_TELEMETRY_DISABLED=1 CI=1
export GIT_SSH_COMMAND="ssh -i $ROOT/etc/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=$ROOT/etc/github_known_hosts -o StrictHostKeyChecking=yes"
log() { echo "$(date -u +%FT%TZ) $*"; }

git -C "$REPO" fetch -q origin "+refs/heads/$BRANCH:refs/heads/$BRANCH"
new=$(git -C "$REPO" rev-parse "$BRANCH")
live=$(cat "$ROOT/app/REVISION" 2>/dev/null || true)
if [ "${1:-}" != "--force" ]; then
  [ "$new" = "$live" ] && exit 0
  # A commit that failed once is not retried every few minutes; the next push (or --force) tries again.
  [ "$new" = "$(cat "$ROOT/deploy.failed" 2>/dev/null || true)" ] && exit 0
fi
log "deploying ${new:0:12} (live: ${live:0:12})"

dest=$REL/$new
rm -rf "$dest" && mkdir -p "$dest"
git -C "$REPO" archive "$new" backend web | tar -x -C "$dest"
echo "$new" > "$dest/REVISION"

fail() { log "deploy of ${new:0:12} failed: $*"; echo "$new" > "$ROOT/deploy.failed"; exit 1; }

# Build while the old release keeps serving; nothing live changes until the symlink moves.
(cd "$dest/web" && corepack pnpm install --frozen-lockfile --silent && corepack pnpm build) \
  > "$ROOT/build.log" 2>&1 || { tail -30 "$ROOT/build.log"; fail "web build"; }
"$ROOT/venv/bin/pip" install -q "$dest/backend" || fail "pip install"

prev=$(readlink -f "$ROOT/app")
switch() {
  ln -sfn "$1" "$ROOT/app.next" && mv -T "$ROOT/app.next" "$ROOT/app"
  sudo /usr/bin/systemctl restart verytas-api
  sudo /usr/bin/systemctl restart verytas-web
}
healthy() {
  for _ in $(seq 1 30); do
    if curl -fs -o /dev/null http://127.0.0.1:8000/health && curl -fs -o /dev/null http://127.0.0.1:3000/signin; then
      return 0
    fi
    sleep 2
  done
  return 1
}

switch "$dest"
if ! healthy; then
  log "new release unhealthy; rolling back to $(basename "$prev")"
  "$ROOT/venv/bin/pip" install -q "$prev/backend" || true
  switch "$prev"
  healthy || log "rollback is unhealthy too; needs a look"
  fail "health check"
fi
rm -f "$ROOT/deploy.failed"
log "live: ${new:0:12}"

# Prune old releases, never the live one.
ls -1dt "$REL"/*/ | tail -n +$((KEEP + 1)) | while read -r old; do
  [ "$(readlink -f "$old")" = "$(readlink -f "$ROOT/app")" ] || rm -rf "$old"
done
