<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
  <img src="docs/assets/logo-light.svg" alt="Verytas logo" width="112">
</picture>

# Verytas

**Brand review that shows its work.**

Verytas checks every post, caption, image, document and video against a brand's own rules and approved facts *before* it is published, explains each problem with a citation, suggests the smallest fix, and leaves the final call to a person.

[**Try the live demo**](https://verytas.pages.dev) · [Architecture](docs/architecture.md) · [Problem statement](docs/problem-statement.md)

![CI](https://github.com/varadarajjborkar/verytas/actions/workflows/ci.yml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)

</div>

<p align="center"><img src="docs/assets/review.png" alt="A piece open in the review queue: the caption with issues marked in place, and a checklist explaining each one with its rule and source" width="900"></p>

## The problem

A brand works with dozens of creators and agencies who post every day, in many languages and formats. One wrong number, a leaked product codename or a snide line about a competitor can cost real money and trust. Checking all of it by hand doesn't scale, and generic AI checkers flag things without saying *why*, so people stop trusting them.

## What Verytas does

| Capability | What it means |
| --- | --- |
| **Reads everything in a post** | The caption, text inside images (OCR), every page of a PDF or Word file (including text drawn as shapes), and video: on-screen text, subtitles and speech. |
| **Sees what is in the pictures** | Finds the brand's mascots even when an AI has redrawn them and names what changed (a wrong colour, an extra eye, a missing tail), with the box and, in video, the time range. Identifies faces against the brand's approved people and flags anyone shown without an agreement. |
| **Checks it against the brand's own sources** | Approved facts with validity dates, banned and preferred words, confidential terms, official artwork, tone, accessibility and AI-disclosure rules. |
| **Explains every flag** | Each issue quotes the exact passage and cites the rule or fact behind it, with page numbers. No unexplained scores. |
| **Fixes, not just flags** | It swaps a phrase, rewrites a sentence or removes a dig, whichever the rule needs, and a judge that knows the rule checks the offer and call to action survive. One click applies it. |
| **Keeps people in charge** | Creators can dispute a reading; the brand team approves, sends back or overrides, and every override needs a written reason. |
| **Learns from decisions** | Rules that reviewers keep overriding are surfaced as unclear, and model-judged rules tune how confident they must be before flagging. |

## Try it in 60 seconds

1. Open **[verytas.pages.dev](https://verytas.pages.dev)** and pick a person at *Kitepath*, a made-up online learning brand with three weeks of history.
2. As **Dev Sharma** (creator), open *My reviews*, paste a caption like *"Kitepath has 2 million learners. Guaranteed results!"* and run it. The claim is checked against the approved fact (1.2 million), a fix appears, and the promise is flagged. Apply the fixes and send it for approval.
3. Use **Switch account** to become **Arjun Mehta** (brand team). Your piece is now in the review queue, ranked by what needs attention first. Approve it, or send it back with a note.

<p align="center"><img src="docs/assets/dashboard.png" alt="The brand team's dashboard: pieces waiting for a decision, creators, escalations and findings over time" width="900"></p>

## How a review works

```mermaid
sequenceDiagram
    autonumber
    actor C as Creator
    participant W as Web app
    participant A as API
    participant P as Prism (review engine)
    participant M as Language and vision models
    actor B as Brand team

    C->>W: Writes a post, attaches images, PDFs or video
    W->>A: Submit (an intake check flags anything unusual for the channel)
    A->>P: Start a review
    P->>P: Split into parts, read text locally (OCR, speech to text)
    P->>P: Rule checks: facts, words, confidential terms, artwork
    P->>P: Compare the parts: the caption, image text, voice-over and on-screen text must agree
    P->>M: Meaning checks, with confidential terms redacted first
    M-->>P: Candidate issues, each quoting real text
    P->>P: An independent judge confirms each one, then findings are signed
    P-->>W: Issues in place, ranked P1 to P3, each with its source and a fix
    C->>W: Applies fixes or disputes a reading, then sends for approval
    B->>W: Approves, sends back or overrides with a reason
    W->>A: Every step is written to a tamper-evident audit log
```

## Architecture

```mermaid
flowchart LR
    subgraph People
        direction TB
        CR["Creators<br/>Studio app"]:::client
        BT["Brand team<br/>Brand Console app"]:::client
    end

    subgraph Web["Next.js server"]
        direction TB
        UI["Pages and components"]:::web
        BFF["Backend for frontend<br/>holds the session token,<br/>forwards an allowlist of routes"]:::web
    end

    subgraph Backend["FastAPI service"]
        direction TB
        API["REST API<br/>roles and clearance<br/>checked on every call"]:::api
        PRISM["Prism<br/>one agent per part of the post"]:::core
        CHECKS["Checkers<br/>facts, words, artwork,<br/>tone, accessibility"]:::core
        GUARD["Safety layer<br/>redaction, guardrails,<br/>signed findings"]:::sec
    end

    LOCAL["Local media tools<br/>OCR, speech to text,<br/>image matching, faces, PDF"]:::local
    VISION["Vision worker<br/>finds and compares mascots<br/>(wakes on demand)"]:::local
    MODELS["Ollama Cloud<br/>gpt-oss, gemma4 vision"]:::ext
    DB[("Database<br/>rules, facts, reviews,<br/>hash-chained audit log")]:::data

    CR & BT --> UI --> BFF --> API --> PRISM
    PRISM --> CHECKS
    PRISM --> LOCAL
    PRISM --> VISION
    PRISM --> GUARD -- "redacted text and pixels" --> MODELS
    API & PRISM --> DB

    style People fill:#f8fafc,stroke:#94a3b8,color:#334155
    style Web fill:#f8fafc,stroke:#94a3b8,color:#334155
    style Backend fill:#f8fafc,stroke:#94a3b8,color:#334155
    classDef client fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef web fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef api fill:#e0e7ff,stroke:#3b5bdb,color:#1e2a78
    classDef core fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef sec fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef local fill:#f1f5f9,stroke:#64748b,color:#1e293b
    classDef ext fill:#f3f4f6,stroke:#6b7280,color:#111827
    classDef data fill:#fef3c7,stroke:#d97706,color:#78350f
```

- **Two apps, one codebase.** Creators get *Studio*; the brand team gets the *Brand Console*. The API enforces the split on every call, so a creator can never open another creator's work.
- **The browser never holds an API key.** The Next.js server keeps the session token and forwards only an allowlisted set of routes.
- **Prism** splits a submission into its parts and spawns an agent for each one: a PDF gets an agent per page, every image inside it gets its own OCR and artwork agents, and every piece of text found goes through the same checks as typed text. Depth and agent counts are capped, and anything cut off is reported as *not checked* rather than silently passed.
- **Rules before models.** Facts, words, confidential terms and artwork are checked deterministically. Models only handle meaning (tone, implied claims, sarcasm), and a model-only finding can never block a post on its own.

## System design

```mermaid
flowchart LR
    U["Visitor's browser"]:::client
    CF["Cloudflare Pages<br/>verytas.pages.dev<br/>pass-through worker"]:::edge

    subgraph AWS["AWS EC2, Mumbai"]
        direction TB
        CAD["Caddy<br/>HTTPS, security headers"]:::web
        NX["Next.js<br/>:3000"]:::web
        FA["FastAPI + Prism<br/>:8000"]:::api
        SQ[("SQLite<br/>+ media blobs")]:::data
        TM["Deploy timer<br/>every 3 min"]:::ops
        VW["Vision worker<br/>stops itself when idle"]:::api
        CAD --> NX --> FA --> SQ
        FA -- "starts it when needed" --> VW
    end

    OL["Ollama Cloud<br/>models over HTTPS"]:::ext

    subgraph GH["GitHub"]
        direction TB
        DEV["dev branch"]:::ops
        MAIN["main = production"]:::ops
        CI["CI: tests, lint, build,<br/>secret scan, dependency audit"]:::ops
        LIVE["live branch"]:::ops
        DEV --> MAIN --> CI -- "all green" --> LIVE
    end

    U --> CF --> CAD
    FA -- "redacted requests" --> OL
    TM -- "pulls with a read-only key,<br/>builds, health-checks,<br/>rolls back on failure" --> LIVE

    style AWS fill:#f8fafc,stroke:#94a3b8,color:#334155
    style GH fill:#f8fafc,stroke:#94a3b8,color:#334155
    classDef client fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef edge fill:#fff7ed,stroke:#ea580c,color:#7c2d12
    classDef web fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef api fill:#e0e7ff,stroke:#3b5bdb,color:#1e2a78
    classDef data fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef ext fill:#f3f4f6,stroke:#6b7280,color:#111827
    classDef ops fill:#dcfce7,stroke:#16a34a,color:#14532d
```

| Decision | Why |
| --- | --- |
| **Pull-based deploys** | The server pulls a branch that only CI can move, with a read-only key. No inbound SSH from CI, and a commit that fails any check never ships. Each release builds beside the live one and rolls back automatically if it fails its health checks. |
| **Heavy media work stays local** | OCR, speech to text, PDF rendering and artwork matching run on the server's CPU, so raw images and audio never leave the machine. Only redacted text and pixels go to a model. |
| **Bounded concurrency everywhere** | A shared pool of model slots, a cap on reviews running at once, and per-step deadlines. A burst of uploads queues instead of exhausting memory or hammering a provider. |
| **Circuit breakers on every model** | If a provider is down, its checks are marked *degraded* on the review instead of failing the whole thing or pretending they passed. |
| **Vision on a worker that sleeps** | Finding redrawn mascots needs three image models and torch, too heavy for the always-on server. They run on a second instance that the API starts on the first review needing it and that stops itself after 20 idle minutes, so it costs nothing most of the time. It installs from GitHub alone and holds no brand data. |
| **One cheap server** | One small ARM instance behind a free edge, with an AWS budget that stops it at a hard cap. The demo runs on credits, at no cost to the team. |

## Tech stack

| Layer | Tools |
| --- | --- |
| **Frontend** | Next.js 16 (App Router, React 19), Tailwind CSS 4, OpenUI for generated answers in *Ask Verytas* |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2 (async), SQLite (Postgres-ready), Pydantic |
| **AI models** | Ollama Cloud: `gpt-oss:120b` and `gpt-oss:20b` for language, `gemma4:31b` for vision. Swappable for TypeSafe Jev or Anthropic Claude |
| **Media, all local** | RapidOCR (ONNX Runtime), faster-whisper, OpenCV (with YuNet and SFace for faces), pdfium, PyAV |
| **Vision worker** | Grounding DINO (tiny), SAM 2.1 (tiny), DINOv2 (small) on PyTorch CPU, on an EC2 Graviton instance that wakes on demand |
| **Security** | Ed25519-signed findings, SHA-256 hash-chained audit log, text and pixel redaction, input guardrails, CSP |
| **Infra and delivery** | AWS EC2, Caddy, systemd, Cloudflare Pages, GitHub Actions (pinned to commit SHAs), gitleaks, pip-audit, pnpm audit |
| **Testing** | pytest (offline, no keys needed), a black-box simulator that tests only through the public API |

## Trust and security

- **Every finding is signed** when it is made, so an edited verdict shows as tampered.
- **Every action is logged** in a hash-chained audit log; changing or deleting an old entry breaks the chain, and anyone with audit access can verify it.
- **Confidential terms never reach a model**: they are redacted from text and blacked out in image pixels first. Confidential-tier content is never sent as pixels at all.
- **People's faces follow the brand's records.** A face is identified against the approved-people library; public portraits are looked up only when the brief names someone and the content isn't confidential.
- **What people type is screened too.** Bribes, "WhatsApp me" style contact swaps and instructions aimed at the AI are refused before they are stored.
- **Access follows role and clearance**, checked on the server on every request, including in the audit log.
- **Audited.** A security review with the Cloudflare security-audit method ran on this codebase; its confirmed findings and the leads it raised are fixed, each with a regression test. The [security report](docs/security/README.md) lists every item, the commit that fixed it, and what is still open.
- **Locked dependencies.** The backend and the vision worker install from hashed lock files, and model files are pinned by SHA-256, so production runs exactly what the tests ran.
- **The live site is reviewed too.** Role checks, cross-site refusals, the browser-only route allowlist, cookie flags and the shipped bundles were checked against the deployed demo; what it found is fixed and listed in the security report.

## Quality

- **Over 550 backend tests** run fully offline in about a minute, plus type checks, lint and a production build for the web apps, all on every push.
- **Measured, not guessed.** The [explain-and-fix eval](backend/evals/explain_and_fix.py) runs the production path on 73 findings with two independent graders: the rule-aware fix pipeline took useful fixes **from 45% to 82%** on the same model. The [mascot benchmark](backend/evals/mascots) runs 425 generated scenes through the vision chain: every character found, defects named in 73 to 100% of cases.
- **Parts compared with each other.** A caption that says 50% off over a poster that says 30%, or a voice-over saying 499 rupees while the screen shows Rs 999, is one finding citing both. On the [cross-source benchmark](backend/evals/crossmodal) it caught 14 of 14 planted contradictions with 0 false alarms on 14 controls. Must rules also get a [second look](backend/evals/second_look) from the larger model, which was right on 30 of 32 hard cases against 27 for the small judge alone. A model-judged finding also shows what reviewers decided before on similar words (precedent memory), and every finding how often reviewers agreed with ones like it (calibration).
- **Tested from the outside.** [`blackbox/`](blackbox/README.md) is a simulator that knows Verytas only through its API. It invents brands, writes posts, images, PDFs and video with planted violations, and steers each round toward what Verytas misses. Across a 216-case campaign, recall on core checks rose **from 78% to 96%**, false alarms on clean posts fell **from 7% to 0%**, and server errors fell **from 17 to 0**, even at 32 parallel submissions.

## What comes next

- **One-on-one meetings.** A creator asks the manager who looks after them for a meeting by chat, voice or video; the manager accepts or proposes another time or way. Calls go through temporary masked numbers, the way delivery apps connect a rider and a customer, and only the time, the way and an outcome note go on the record. It is designed and previewed in both apps (marked *Planned*), not built: in a demo one person plays both sides, and masked calling needs a paid telephony provider.
- **Managing it all from the console:** an approved-people tab in the Library, a video player with findings on its timeline, and managers marking moments and areas with comments (the API supports all three today).
- **Sharper visual checks on busy backgrounds**, where the cut-out still takes in some background and raises false alarms, and a GPU for the language and vision models once AWS grants the quota.

## Run it locally

```bash
# Backend on :8000 (tests need no keys)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                 # add OLLAMA_API_KEY for live models
.venv/bin/pytest -q
.venv/bin/python -m verytas.cli seed-showcase --db showcase.db --write-env ../web/.env.local
VERYTAS_DATABASE_URL=sqlite+aiosqlite:///./showcase.db .venv/bin/uvicorn verytas.main:app

# Web apps, each in its own terminal
cd web
pnpm install
pnpm dev:manager                     # Brand Console on :3000
pnpm dev:creator                     # Studio on :3001
```

The seed creates the *Kitepath* brand with seven creators and three weeks of history, and writes their tokens into `web/.env.local`. Without any API keys, model-judged checks fall back to an offline heuristic and every review says so. Without a backend, the web app shows clearly labelled sample data.

## Repository layout

| Path | What is inside |
| --- | --- |
| [`backend/`](backend) | FastAPI service: checkers, Prism, workflow, insights, security |
| [`web/`](web) | Next.js: the Studio and Brand Console apps |
| [`blackbox/`](blackbox) | The black-box simulator |
| [`deploy/`](deploy) | Server setup, pull-based deploys, the edge worker ([how it works](deploy/README.md)) |
| [`docs/`](docs) | Problem statement and the full architecture |

## Working agreement

- `main` is production, and merging into it deploys. `dev` is the integration branch.
- Templates, external services and significant AI assistance are disclosed, per the challenge rules.
