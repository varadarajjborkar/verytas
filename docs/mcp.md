# Verytas over MCP

Verytas can be used from your own AI client (Claude Desktop, Claude Code, or any client that speaks the
[Model Context Protocol](https://modelcontextprotocol.io)) with a **personal token**. The client acts as you
and never as more than you: it reads what you can read, submits and comments the way you can, and cannot
decide, approve or publish. Those stay in the app, where a person makes them.

The endpoint is `/mcp` on the same address as the app, over the Streamable HTTP transport (stateless, JSON
responses). It is built on the official Python SDK (`mcp` 1.30.0, pinned in `backend/requirements.lock`).

## Make a token

1. Sign in, open **Settings**, then the **Tokens** tab.
2. Give it a name, choose **Read only** or **Read and write**, and an expiry of 7, 30 or 90 days.
3. Copy the token from the panel that appears. It is shown once; if you lose it, revoke it and make another.

A token starts with `vt_pat_`. You can hold up to five active tokens. Revoke one at any time and it stops
working on the next request. The same can be done over the API (`POST`, `GET` and `DELETE /me/tokens`) with
your web session.

## Connect a client

Claude Code:

```bash
claude mcp add --transport http verytas https://YOUR-VERYTAS-ADDRESS/mcp \
  --header "Authorization: Bearer vt_pat_..."
```

Claude Desktop (and other clients that read an `mcpServers` config; `mcp-remote` bridges clients that only
launch local servers):

```json
{
  "mcpServers": {
    "verytas": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://YOUR-VERYTAS-ADDRESS/mcp",
               "--header", "Authorization: Bearer ${VERYTAS_TOKEN}"],
      "env": { "VERYTAS_TOKEN": "vt_pat_..." }
    }
  }
}
```

Keep the token out of files you share or commit; treat it like a password.

## Tools

Read tools (token scope `read`; each is annotated read-only):

| Tool | What it returns |
| --- | --- |
| `whoami` | Your name, role, effective clearance, company, and this token's scopes and expiry. |
| `list_content` | Pieces with status and latest review outcome, newest activity first. Filter by `status`; `limit` up to 50. A creator sees their own pieces; brand-team roles see what their clearance allows. |
| `get_review` | A piece's latest version text and the findings from its latest review: level, title, explanation, quote, the rule cited and a suggested rewrite. |
| `list_rules` | The active brand rules you can see, with their text and examples. |
| `search` | Pieces, findings and rules you can open, by plain text. |
| `precheck_text` | The intake pre-check on a draft (length, hidden characters and the like). Stores nothing and runs no review. |

Write tools (token scope `write`):

| Tool | What it does |
| --- | --- |
| `submit_content` | Submits text as a new piece, as you, and starts the automated review. Call `get_review` shortly after to read the findings. Text only. |
| `add_comment` | Comments on a piece you can open. The text is screened like any comment in the app. |

## Security model

A token can only narrow what its person can do. It never widens it.

- **Separate audiences.** A `vt_pat_` token is accepted only at `/mcp`; every REST route refuses it. A web
  session token is refused at `/mcp`. They live in different tables, so neither lookup can find the other's
  hash. A personal token also cannot manage tokens: that is REST-only, behind the web session, so a leaked
  token cannot extend its own life.
- **Stored as a hash.** Only the SHA-256 of a token is stored. The secret is returned once, at creation, and
  appears in no listing, log or audit entry.
- **Checked on every request.** The token must exist, be unrevoked and unexpired (30 days by default, 90 at
  most), and its person must still belong to the workspace it was made in. A failure is a uniform `401` with a
  `WWW-Authenticate: Bearer` header; the caller is not told which check failed.
- **Same access rules as the app.** Tools call the same functions the REST routes use: a creator cannot read
  another creator's piece (it is reported as not found), roles gate the same actions, and submissions go
  through the same validation, intake check, review start and self-serve budget. Role and clearance are read
  fresh on each call, so a change applies immediately.
- **A clearance ceiling.** Material leaves Verytas for a third party's AI client, so a token reads at most
  the `internal` tier by default, whatever the person's own clearance (`VERYTAS_MCP_MAX_TIER` raises it).
  Confidential-tier pieces and rules do not appear in any result.
- **Confidential terms never appear.** Every string in every result is passed through the same redaction used
  before text goes to a model, so a codename that sits in a piece or a finding comes back as `[[TERM_1]]`.
  There is no tool that lists terms.
- **Scopes.** A read-only token that calls a write tool gets a tool error, not a crash, and the attempt is
  audited.
- **Rate limit.** 60 tool calls a minute per token, counted in the API process (`VERYTAS_MCP_CALLS_PER_MINUTE`).
- **Origin check.** A request that carries an `Origin` header is refused unless that origin is listed in
  `VERYTAS_MCP_ALLOWED_ORIGINS` (empty by default). AI clients are not browsers and send no `Origin`, so they
  pass; a web page, including one using DNS rebinding, does not. The check runs before the token is read.
  The request body is capped at 1 MB.
- **Audited.** Each tool call is appended to the hash-chained audit log as `mcp.tool` with the tool name,
  whether it succeeded and the token id. Arguments are never recorded, since they can hold content. Token
  creation and revocation are audited too, without the secret.
- **Returned text is data.** Titles, text, quotes, explanations and comments come from people and from checks.
  The server's instructions and each tool's description tell the client to read them as data, never as
  instructions; this lowers the risk of prompt injection from stored content but does not remove it, so give
  a write-scope token only to a client you trust with your account.

## Deliberately left out

- Deciding on, dismissing or applying findings, approving, requesting changes, publishing or withdrawing. A
  person decides, in the app. This is a core principle of the product, not a missing feature.
- Admin and library editing: rules, facts, assets, events, people, users.
- Confidential terms, in any form.
- Token management.
- Files, images and video. Submission is text only.
- Anything the person's role cannot do through the REST API.

## Operating notes

- Settings: `VERYTAS_MCP_ENABLED` (default on), `VERYTAS_MCP_ALLOWED_ORIGINS`, `VERYTAS_MCP_CALLS_PER_MINUTE`,
  `VERYTAS_MCP_MAX_TIER`.
- The public server's reverse proxy sends `/mcp` to the API (`deploy/Caddyfile`); every other path still goes
  to the web app. The rate limit and `last_used_at` throttle are per process, which suits the single-process
  deployment; a multi-worker deployment would need them in Redis.
- The SDK is pinned to 1.x on purpose. The 2.x line is a recent rewrite with a different HTTP stack.
