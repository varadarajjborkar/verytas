# Deploying the Verytas demo

One small ARM server (AWS t4g.medium, Mumbai) runs everything judges touch:

| Piece | Where | Notes |
|---|---|---|
| HTTPS | Caddy (`Caddyfile`) | Let's Encrypt certificate for the server's sslip.io name; security headers |
| Web | `verytas-web.service` | `next start` on 127.0.0.1:3000; sign-in on, with the demo's account picker |
| API | `verytas-api.service` | uvicorn on 127.0.0.1:8000; SQLite in `/srv/verytas/data` |
| Demo reset | `verytas-reset.timer` | daily check; reseeds when the data is 14 days old (`reset-demo.sh --force` to do it now) |

OCR (RapidOCR), artwork matching (OpenCV), video decoding (PyAV) and speech (faster-whisper) run on the
server's CPU. The language and vision models are reached over HTTPS, after confidential terms are
redacted. Nothing listens publicly except Caddy on 80 and 443.

Secrets live only on the server, in `/srv/verytas/etc/{api,web}.env` (mode 600), and in the seeded
demo-accounts file. None of them is in this folder.

`deploy.sh` ships the committed tree, rebuilds and restarts. Spend is capped by an AWS budget that stops
the server automatically at its limit.
