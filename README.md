# Verytas: brand-governance platform (Inkloom AI challenge)

Verytas reviews content before it is published. It checks drafts against a company's approved rules,
time-valid facts and confidential terms, explains every issue with a citation, suggests the smallest
fix, and routes the content through a human approval workflow. It also learns which guidelines are
unclear from how reviewers override them.

- Problem statement: [`Problem_statement.pdf`](Problem_statement.pdf) · readable copy in [`docs/problem-statement.md`](docs/problem-statement.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Round 1 checklist: [`docs/round1-checklist.md`](docs/round1-checklist.md)

## Repository layout

| Path | What |
|---|---|
| `backend/` | FastAPI service: checks, Prism orchestrator, review workflow, insights, security (Python 3.12+) |
| `web/` | Next.js 16 frontend on OpenUI: dashboard, review workspace, guideline health, Ask Verytas |
| `docs/` | Problem statement, architecture, submission checklist |

## Run locally

Backend (port 8000):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env              # add OLLAMA_API_KEY (and TYPESAFE_API_KEY for Jev) if you have them
.venv/bin/uvicorn verytas.main:app --reload
.venv/bin/pytest -q               # full suite runs offline, no keys needed
```

First run: `POST /bootstrap` creates the workspace and returns an admin token (interactive docs at `/docs`).

Frontend (port 3000):

```bash
cd web
pnpm install
cp .env.example .env.local        # VERYTAS_API_URL + VERYTAS_API_TOKEN for live data; OLLAMA_API_KEY for /ask
pnpm dev
```

Without backend settings the frontend runs on clearly labelled demo data.

## Models and external services (disclosure)

| Service | Used for | When |
|---|---|---|
| Ollama Cloud (`gpt-oss:120b`, `gpt-oss:20b`) | claim extraction, explanations, minimal-edit fixes, Ask Verytas | when `OLLAMA_API_KEY` is set |
| TypeSafe Jev (`jev-1.13.0`) | semantic rule judgement, intent checks | when `TYPESAFE_API_KEY` is set; otherwise an offline heuristic, shown as "degraded" |
| Anthropic Claude | optional alternative LLM backend | only with `VERYTAS_LLM_BACKEND=claude` |
| Sentry | error monitoring (no request bodies, no PII) | only when `SENTRY_DSN` is set |

Confidential terms and personal data are redacted before any text leaves the service.

## Working agreement

- `main` is production: anything merged there gets deployed. `dev` is the integration branch for the team.
- Work on a feature branch (or directly on `dev` for small changes) and open PRs into `dev`. Promote `dev` to `main` only when it is demo-ready.
- Commit small and often from your own account, since judges may inspect commit history.
- Disclose templates, boilerplate, external services and significant AI assistance (see rules in the problem statement).
