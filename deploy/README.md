# Deploying the Verytas demo

One small ARM server (AWS t4g.medium, Mumbai) runs everything judges touch:

| Piece | Where | Notes |
|---|---|---|
| Public address | Cloudflare Pages (`edge/_worker.js`) | `verytas.pages.dev`, free tier; passes every request through to the server |
| HTTPS | Caddy (`Caddyfile`) | Let's Encrypt certificate for the server's sslip.io name; security headers |
| Web | `verytas-web.service` | `next start` on 127.0.0.1:3000; sign-in on, with the demo's account picker |
| API | `verytas-api.service` | uvicorn on 127.0.0.1:8000; SQLite in `/srv/verytas/data` |
| Document previews | `verytas-convert.socket` | LibreOffice in a sealed per-file service; see below |
| Deploys | `verytas-deploy.timer` | every 3 minutes: if `live` (main after CI) moved, build it, switch, health-check, roll back on failure |
| Demo reset | `verytas-reset.timer` | daily check; reseeds when the data is 14 days old (`reset-demo.sh --force` to do it now) |

OCR (RapidOCR), artwork matching (OpenCV), video decoding (PyAV) and speech (faster-whisper) run on the
server's CPU. The language and vision models are reached over HTTPS, after confidential terms are
redacted. Nothing listens publicly except Caddy on 80 and 443.

Secrets live only on the server, in `/srv/verytas/etc/{api,web}.env` (mode 600), and in the seeded
demo-accounts file. None of them is in this folder. Both env files may carry `OLLAMA_API_KEY_FALLBACK`, a
second account's key that the API and the web's model routes switch to (for ten minutes at a time) when
the first is refused or out of quota.

**`main` is production.** Pushing to `main` runs CI (`.github/workflows/ci.yml`: backend lint and tests,
web type check, lint and build, a secret scan and dependency audits). When every job passes, CI moves the
`live` branch to that commit. The server holds a read-only deploy key and pulls `live` itself
(`autodeploy.sh`), so nothing needs inbound SSH from CI, and a commit that fails a check never deploys. Each commit is built in
`/srv/verytas/releases/<sha>` while the old one keeps serving; `/srv/verytas/app` is a symlink that moves
only after the build succeeds, and moves back if the new release fails its health checks. The three most
recent releases are kept. A commit that failed is not retried until something new lands on `main` (or
`deploy.sh --force`). `deploy.sh` triggers a deploy now instead of waiting for the timer.

Spend is capped by an AWS budget that stops both instances automatically at its limit.

**Own accounts.** Beside the seeded companies, visitors can sign up (`/signin/account`): a brand team makes
a new, empty company and gets a join code; a creator joins with it. Turn it on with
`VERYTAS_SELF_SIGNUP=true` in `api.env`. Every such company can spend model calls, so it is bounded by
`VERYTAS_SELF_SIGNUP_MAX_WORKSPACES` (200), `VERYTAS_SELF_SIGNUP_PER_HOUR` (30) and a daily budget of
model-spending actions, `VERYTAS_SELF_SERVE_ACTIONS_PER_DAY` (60 per company) and
`VERYTAS_SELF_SERVE_ACTIONS_PER_DAY_TOTAL` (600 for all of them). The sign-in page offers it only when the
API says it is on. Companies made this way are wiped with everything else at the 14-day reset.

The public address is a Cloudflare Pages project whose only file is a pass-through worker, so it never
needs redeploying when the app changes. It restates our own Origin as the server's, which keeps the
app's cross-site write check meaningful, and rewrites redirects back to the public name. Publish it with
`wrangler pages deploy deploy/edge --project-name verytas --branch main`. Uploads through it are capped
at Cloudflare's 100 MB; the sslip.io address still takes the app's full 150 MB.

## The vision worker

Finding redrawn mascots needs Grounding DINO, SAM 2.1 and DINOv2 on PyTorch, which the server can't
carry. They run on a second instance (c7g.large, same subnet) that is stopped most of the time:

| Piece | Notes |
|---|---|
| Setup | `vision.sh` is the instance's user data. It installs itself as the boot script, so every boot takes the same path: fetch `live` with a read-only deploy key, install `backend/requirements-vision.lock` with `--require-hashes` when it changed (SAM2 from its pinned commit), fetch the models, then start the worker |
| Worker | `verytas-vision.service`: `python -m verytas.vision.worker` on port 8100, as an unprivileged user that can write only its models, cache and state; it starts only after a successful update |
| Waking | The API starts the instance through its own instance role (`verytas/vision/wake.py`) when a review needs it, and waits for `/health`, which answers only once the models are loaded |
| Sleeping | `verytas-vision-idle.timer` stops the instance after 20 idle minutes, read from a file the worker touches on every request; never mid-install, and within an hour if the worker never comes up |
| Secrets | `/verytas/vision/token` and `/verytas/vision/deploy_key` in SSM Parameter Store. The API reads the same token from `VERYTAS_VISION_WORKER_TOKEN` in `api.env`, beside `VERYTAS_VISION_WORKER_URL` (the worker's private address) and `VERYTAS_VISION_WORKER_INSTANCE_ID` |
| Network | Its security group admits port 8100 from the API server's group only; it has no public service |

Without those three settings the API runs as before and every review with mascot artwork says redrawn
mascots were not looked for.

## Document previews (LibreOffice)

Word and PowerPoint previews are converted to PDF by LibreOffice, which reads files strangers upload, so
it never runs inside the API. It is a separate socket-started service:

| Piece | Notes |
|---|---|
| Packages | `apt-get install --no-install-recommends libreoffice-writer-nogui libreoffice-impress-nogui fonts-dejavu-core fonts-liberation2` (about 500 MB) |
| Converter | `convert.py`, installed root-owned as `/usr/local/lib/verytas/convert.py`; standard library only, run by the system Python |
| Socket | `systemd/verytas-convert.socket`: `/run/verytas-convert.sock`, mode 600, owned by `verytas`, one connection at a time |
| Service | `systemd/verytas-convert@.service`: one process per file, `DynamicUser`, `PrivateNetwork`, no view of `/srv/verytas`, no capabilities, 1.5 GB memory, 64 tasks, 150% CPU, 120 s |

Install or update:

```bash
sudo install -D -o root -g root -m 0755 deploy/convert.py /usr/local/lib/verytas/convert.py
sudo install -o root -g root -m 0644 deploy/systemd/verytas-convert.socket \
  'deploy/systemd/verytas-convert@.service' /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now verytas-convert.socket
```

The API sends a file there when `/run/verytas-convert.sock` exists (`VERYTAS_CONVERT_SOCKET` to change
the path), after cutting every reference to anything outside it. Without the socket it runs LibreOffice
itself if installed (development), and otherwise answers that previews need LibreOffice; PDF previews
need nothing extra.
