# Deploying the Verytas demo

One small ARM server (AWS t4g.medium, Mumbai) runs everything judges touch:

| Piece | Where | Notes |
|---|---|---|
| Public address | Cloudflare Pages (`edge/_worker.js`) | `verytas.pages.dev`, free tier; passes every request through to the server |
| HTTPS | Caddy (`Caddyfile`) | Let's Encrypt certificate for the server's sslip.io name; security headers |
| Web | `verytas-web.service` | `next start` on 127.0.0.1:3000; sign-in on, with the demo's account picker |
| API | `verytas-api.service` | uvicorn on 127.0.0.1:8000; SQLite in `/srv/verytas/data` |
| Deploys | `verytas-deploy.timer` | every 3 minutes: if `live` (main after CI) moved, build it, switch, health-check, roll back on failure |
| Demo reset | `verytas-reset.timer` | daily check; reseeds when the data is 14 days old (`reset-demo.sh --force` to do it now) |

OCR (RapidOCR), artwork matching (OpenCV), video decoding (PyAV) and speech (faster-whisper) run on the
server's CPU. The language and vision models are reached over HTTPS, after confidential terms are
redacted. Nothing listens publicly except Caddy on 80 and 443.

Secrets live only on the server, in `/srv/verytas/etc/{api,web}.env` (mode 600), and in the seeded
demo-accounts file. None of them is in this folder.

**`main` is production.** Pushing to `main` runs CI (`.github/workflows/ci.yml`: backend lint and tests,
web type check, lint and build, a secret scan and dependency audits). When every job passes, CI moves the
`live` branch to that commit. The server holds a read-only deploy key and pulls `live` itself
(`autodeploy.sh`), so nothing needs inbound SSH from CI, and a commit that fails a check never deploys. Each commit is built in
`/srv/verytas/releases/<sha>` while the old one keeps serving; `/srv/verytas/app` is a symlink that moves
only after the build succeeds, and moves back if the new release fails its health checks. The three most
recent releases are kept. A commit that failed is not retried until something new lands on `main` (or
`deploy.sh --force`). `deploy.sh` triggers a deploy now instead of waiting for the timer.

Spend is capped by an AWS budget that stops both instances automatically at its limit.

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
