# Verytas web

Next.js 16 (App Router) frontend for Verytas. UI components and generative UI come from
[OpenUI](https://github.com/thesysdev/openui) (`@openuidev/react-ui`, `@openuidev/react-lang`).

| Route | What it does |
|---|---|
| `/` | Governance dashboard: findings trend, pipeline, top rules, recurring problems, unclear guidelines |
| `/review` | Paste a draft, run a review, see highlighted findings with citations and minimal-edit fixes, accept or dismiss |
| `/guidelines` | Guideline health: which rules reviewers override or disagree about, with advice |
| `/ask` | "Ask Verytas": questions answered as live OpenUI charts and tables from the insights data |

## Run

```bash
pnpm install
cp .env.example .env.local   # then fill in values
pnpm dev                      # http://localhost:3000
```

Without `VERYTAS_API_URL`/`VERYTAS_API_TOKEN`, every page uses clearly labelled demo data.
`/ask` needs `OLLAMA_API_KEY`; the key stays on the server and is never sent to the browser.

The OpenUI Lang system prompt for `/ask` is generated from the component library into
`src/generated/openui-prompt.ts` by `pnpm gen:prompt` (also runs before `dev` and `build`).

## Provenance

Scaffolded with `create-next-app` (Next.js 16.4, TypeScript, Tailwind v4, ESLint). Everything under
`src/` apart from the generated prompt was written for this project.
