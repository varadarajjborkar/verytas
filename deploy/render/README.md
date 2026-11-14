# Free deployment

Since 14 Nov 2026 the demo runs on free tiers only, with no card on any account:

| Piece | Where | Notes |
|---|---|---|
| Public address | Cloudflare Pages, `verytas.pages.dev` | `deploy/edge/_worker.js` passes every request to Vercel |
| Web app | Vercel Hobby, project `verytas` (root `web`, region `sin1`) | Deploys `main` on push |
| API | Render free web service `verytas-api` (Singapore, 512 MB, 0.1 CPU) | Deploys `main`; starts with `deploy/render/start.sh` |
| Database | Neon free, project `verytas` (Singapore, Postgres 16) | Sleeps when idle; 0.5 GB |
| Models | NVIDIA's hosted models (`VERYTAS_LLM_BACKEND=nvidia`) | About 40 requests a minute for the account |
| Keep-awake | Cloudflare cron `deploy/keepwarm` | `/health` every 10 minutes, so Render never sleeps |

Render's disk is wiped on every restart, so nothing the API needs may live on it. The data is in Neon,
and the keys come in through `VERYTAS_KEYS_TGZ`: the seed's keys folder as a base64 tar.gz, files at the
top level. They must be the keys the data was seeded with. Without them messages read as unreadable and
finding signatures fail, so the start script refuses to run without every one. Inki's memory is kept in
`/tmp` and starts empty after a restart.

The API runs small: `VERYTAS_ASSET_MATCHING=false`, `VERYTAS_FACES_ENABLED=false`, `VERYTAS_OCR_THREADS=1`,
`VERYTAS_OCR_MAX_SIDE=736`, `VERYTAS_MEMORY_EMBED_MODEL=hash`, Whisper `tiny`, and `MALLOC_ARENA_MAX=2`.
Reviews say when artwork was not compared. On NVIDIA there is no web search, so unbacked claims are left
for the reviewer, and each review says so.

## Reseeding the demo

Seed on a laptop, where it takes about three minutes, then copy it into Neon. The copy empties Neon first:

```bash
cd backend
python -m verytas.cli seed-showcase --db /tmp/seed/showcase.db --keys-dir /tmp/seed/keys \
  --write-demo-accounts /tmp/seed/demo-accounts.json
python -m verytas.dbcopy sqlite+aiosqlite:////tmp/seed/showcase.db "$NEON_DATABASE_URL"
```

Then hand the new keys to Render (`VERYTAS_KEYS_TGZ`, from `tar -czf - -C /tmp/seed/keys . | base64`) and
the new accounts file to Vercel (`VERYTAS_DEMO_ACCOUNTS_JSON`, the file base64-encoded), and redeploy both.
