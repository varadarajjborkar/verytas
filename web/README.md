# Verytas web

Next.js 16 (App Router) frontend for Verytas. UI components and generative UI come from
[OpenUI](https://github.com/thesysdev/openui) (`@openuidev/react-ui`, `@openuidev/react-lang`).

Two apps from one codebase, one per side: the **Brand Console** for the brand team (`pnpm dev:manager`,
port 3000) and **Studio** for creators (`pnpm dev:creator`, port 3001). The API decides what each side may
see; the apps only lay it out.

| Route | What it does |
|---|---|
| `/` | For a visitor who isn't signed in (when sign-in is on), the landing page; otherwise Home: for the brand team, the dashboard (what is waiting, findings over time, recurring problems); for a creator, their work. First steps for a new account, and a guided tour on the first visit to each side (Settings > Profile replays it) |
| `/review` | The review queue (brand team) or my reviews (creator). A piece opens on the review screen: the text with issues marked in place, the issue list beside it, a bar that walks through them, and attached documents page by page with *Preview* to see them as they look |
| `/escalations` | Questions creators and Prism raised for a person |
| `/conversations` | Conversations between a creator and the brand team beside the piece in question: replies, edits, files, meeting links as Join cards, and @Inki on request |
| `/creators` | Each creator's record (brand team) |
| `/library` | Rules, facts, confidential terms, artwork and Intake, where brand material is handed over and drafted into the library |
| `/guidelines` | Guideline health: which rules reviewers override or disagree about, with a clearer wording drafted on request |
| `/ask` | Ask Inki: questions answered as live charts and tables from the brand's own data |
| `/ai` | How AI is used in Verytas, in plain words |
| `/signin` | The demo's person picker, and `/signin/account` for own accounts |
| `/privacy`, `/terms` | Static pages, served to anyone |

Every browser call goes through `/api/v/...`, a server-side proxy that holds the session token and
forwards only an allowlist of API routes. The two chats, Ask Inki (`api/chat`) and Summarize
(`api/assist`), stream through `src/lib/guard.ts`, which answers requests for their instructions itself and
cuts off a reply that starts reciting them.

## Run

```bash
pnpm install
cp .env.example .env.local   # then fill in values
pnpm dev:manager              # Brand Console on http://localhost:3000
pnpm dev:creator              # Studio on http://localhost:3001
```

Without `VERYTAS_API_URL`/`VERYTAS_API_TOKEN`, every page uses clearly labelled demo data.
`/ask` needs `OLLAMA_API_KEY`; the key stays on the server and is never sent to the browser.

The OpenUI Lang system prompt for `/ask` is generated from the component library into
`src/generated/openui-prompt.ts` by `pnpm gen:prompt` (also runs before `dev` and `build`).

## The landing page

`public/welcome/` holds the landing, privacy and terms pages as static HTML, so they load without the app's
JavaScript. Their CSS is compiled once with Tailwind 3 (`pnpm welcome:css`, from `welcome/tailwind.config.cjs`
and `welcome/in.css`) and the Phosphor icon font is served from the same folder, so nothing is fetched from a
script CDN. `src/proxy.ts` rewrites `/privacy` and `/terms` to them for everyone, and `/` to the landing page
for a visitor without a session when sign-in is required. Rerun `pnpm welcome:css` after changing their
classes.

`next.config.ts` sets `skipProxyUrlNormalize`: behind Caddy, Next otherwise rebuilt the proxy's URL as
`localhost` while comparing rewrites against the address it listens on, treated the rewrite as external and
proxied it to itself over TLS, and the landing page answered 500.

## Provenance

Scaffolded with `create-next-app` (Next.js 16.4, TypeScript, Tailwind v4, ESLint). Everything under
`src/` apart from the generated prompt was written for this project.
