# Verytas

**Brand governance before you hit publish.** Verytas reviews content against a company's approved rules, time-valid facts and confidential terms. It explains every issue with a citation, proposes the smallest fix that keeps the writer's intent, and routes the piece through a human approval workflow. It also learns which guidelines are unclear from how reviewers override them.

Built for the Inkloom AI brand-governance challenge. Brief: [`docs/problem-statement.md`](docs/problem-statement.md) · design: [`docs/architecture.md`](docs/architecture.md)

## What it does

- **Reads everything a post contains.** The caption, images (with local OCR), PDFs and Word files page by page (text layers, scanned pages and screenshots pasted inside them), and video (burned-in captions, on-screen text, subtitle tracks and speech).
- **Checks it all the same way** for banned and preferred wording, brand casing, leaked codenames, outdated or inflated statistics, unsupported claims, tone, AI-disclosure labels and accessibility.
- **Guards the brand's own artwork.** Official logos and mascots are ground truth: altered details, garbled wordmarks, look-alikes and bodies attached to an approved face are flagged, with the pixel region.
- **Reads between the lines.** Context layers widen from a paragraph to the whole post to caption plus image, catching indirect taunts, sarcasm and meanings that depend on the language (Hinglish included).
- **Explains, fixes and keeps humans in charge.** Every finding cites its rule or fact. Creators work through a P1/P2/P3 checklist, apply fixes, dispute misreadings and resubmit; blockers and unread content need a noted override.
- **Learns from the people using it.** Disputes and reviewer decisions tune how sure each model-judged rule must be, and guideline health shows which rules are unclear.

## Architecture

```mermaid
flowchart TB
    subgraph Clients
        direction LR
        UI["Web app<br/>review, dashboard, ask"]:::client
        BB["Black-box simulator<br/>tests via API only"]:::sim
    end

    API["REST API<br/>auth, roles, intake check"]:::api
    DB[("Knowledge store<br/>rules, facts, terms, assets")]:::data
    NOTE["Creator's note<br/>kept apart from checks"]:::note

    subgraph Pipeline["Prism: agents spawned per part"]
        direction LR
        TXT["Text agent<br/>caption, page text"]:::check
        IMG["Image agent<br/>OCR, assets, scene"]:::check
        DOC["Document agent<br/>page agents"]:::check
        VID["Video agent<br/>captions, speech, frames"]:::check
        ONION["Context layers<br/>paragraph to post"]:::core
        DOC --> IMG
        VID --> TXT
        IMG --> TXT
    end

    subgraph Models["Model access"]
        direction LR
        RED["Redaction<br/>text and pixels"]:::sec
        LLM["Ollama Cloud<br/>gpt-oss, gemma4 vision"]:::ext
        RED --> LLM
    end

    subgraph Governance
        direction LR
        SIG["Signed findings<br/>P1, P2, P3"]:::sec
        FLOW["Checklist and approval<br/>disputes, resubmit"]:::api
        AUD["Audit chain<br/>hash-linked log"]:::sec
        LEARN["Learning<br/>rule thresholds, health"]:::api
        SIG --> FLOW --> AUD
        FLOW --> LEARN
    end

    Clients --> API --> Pipeline
    DB --> Pipeline
    Pipeline -. "model calls" .-> Models
    Pipeline --> Governance
    NOTE -. "read only after findings" .-> Governance
    LEARN -. "feeds back" .-> Pipeline

    style Clients fill:#f8fafc,stroke:#94a3b8,color:#334155
    style Pipeline fill:#f8fafc,stroke:#94a3b8,color:#334155
    style Models fill:#f8fafc,stroke:#94a3b8,color:#334155
    style Governance fill:#f8fafc,stroke:#94a3b8,color:#334155

    classDef client fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef sim fill:#fce7f3,stroke:#db2777,color:#831843
    classDef api fill:#ede9fe,stroke:#7c3aed,color:#4c1d95
    classDef core fill:#e0e7ff,stroke:#4f46e5,color:#312e81
    classDef check fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef sec fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef data fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef ext fill:#f3f4f6,stroke:#6b7280,color:#111827
    classDef note fill:#fff7ed,stroke:#ea580c,color:#7c2d12,stroke-dasharray: 4 3
```

**Legend:** blue = clients · purple = API, workflow and learning · green = agents per content type · indigo = context layers · red = security · amber = data · grey = external models · dashed orange = the creator's note, a separate realm · pink = test harness

### How a review flows

1. A creator uploads a caption plus any images, documents and video. Before anything is accepted, the intake check compares it with what the channel normally carries (caption length, page count, image size, video length, hidden characters). Anything irregular needs a reason, and still counts against the score.
2. **Prism** loads the rules, facts and official assets the content's tier may see, then spawns an agent per part. Agents spawn their own: a PDF gets a page agent per page, each pasted screenshot an image agent, each image its OCR, asset and scene agents, and every piece of text found a text agent running the same checks as typed text. Depth and agent counts are capped; anything cut off is reported as not checked.
3. Text is read locally first. Confidential terms are **blacked out in the pixels** before any image or video frame reaches the vision model, and redacted from all text sent to a model. Confidential-tier content never leaves the machine as pixels.
4. **Context layers** then read the whole submission, from paragraphs to the full post to caption plus images. Each candidate must quote real text and pass an independent judge question.
5. Only now is the **creator's note** weighed, and only against model-judged findings. It can cap a far-fetched reading at advisory, never clear a mechanical one; a note that tries to steer the review is escalated.
6. Findings are **signed**, ordered P1 to P3, and shown as a checklist. Creators tick what they fixed, apply suggestions, dispute misreadings and resubmit. Disputes are re-judged layer by layer without the claim in view, and the system can still say no. Every step lands in the **hash-chained audit log**, and outcomes tune each rule's threshold.

## Tested from the outside

[`blackbox/`](blackbox/README.md) is a reality simulator that knows Verytas only through its API. It invents brand worlds, writes roasts, flame wars, Hinglish captions and crisis apologies inside them, and plants violations with exact ground truth, including evasive spellings. A bandit then steers each generation toward what Verytas misses. Its first runs found that public posts skipped the built-in checks, that look-alike letters slipped past banned-term and leak checks, and that parallel submissions hit database deadlocks and 500s.

On a 216-case campaign, core recall rose from 78% to 96%, false positives on controls fell from 7% to 0%, and server errors went from 17 to 0, even at 32 parallel submissions.

## Repository layout

| Path | What |
| --- | --- |
| `backend/` | FastAPI service: checks, Prism, workflow, insights, security (Python 3.12+) |
| `web/` | Next.js 16 on OpenUI: dashboard, review workspace, guideline health, Ask Verytas |
| `blackbox/` | Black-box reality simulator: invents brands, writes posts, images, PDFs and video, grades Verytas |
| `docs/` | Problem statement, architecture, submission checklist |

## Run locally

```bash
# Backend on :8000 (tests run fully offline, no keys needed)
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env              # add OLLAMA_API_KEY for live models
.venv/bin/uvicorn verytas.main:app --reload
.venv/bin/pytest -q

# Frontend on :3000
cd web
pnpm install
cp .env.example .env.local        # VERYTAS_API_URL + VERYTAS_API_TOKEN for live data, OLLAMA_API_KEY for Ask
pnpm dev
```

On first run, `POST /bootstrap` creates the workspace and returns an admin token (interactive docs at `/docs`). Without backend settings, the frontend shows clearly labelled demo data.

## Models and external services

| Service | Used for | When |
| --- | --- | --- |
| Ollama Cloud (`gpt-oss:120b`, `gpt-oss:20b`) | claim extraction, explanations, fixes, the semantic judge, context layers, disputes, Ask Verytas, simulator content | when `OLLAMA_API_KEY` is set |
| Ollama Cloud (`gemma4:31b`) | image and video-frame understanding, asset comparison, OCR fallback | when `OLLAMA_API_KEY` is set; never for confidential-tier content |
| RapidOCR, faster-whisper, OpenCV, pdfium (local) | OCR, speech-to-text, asset matching, PDF rendering | always local; nothing leaves the machine |
| TypeSafe Jev (`jev-1.13.0`) | semantic judge, if preferred | optional, when `TYPESAFE_API_KEY` is set |
| Anthropic Claude | alternative LLM backend | only with `VERYTAS_LLM_BACKEND=claude` |
| Sentry | error monitoring, without request bodies or PII | only when `SENTRY_DSN` is set |

With no keys, semantic checks fall back to an offline heuristic, and the scorecard marks them "degraded" rather than passed.

## Working agreement

- `main` is production; merging into it deploys. `dev` is the integration branch; open PRs into `dev`.
- Commit small and often from your own account, since judges may read the history.
- Disclose templates, boilerplate, external services and significant AI assistance, per the challenge rules.
