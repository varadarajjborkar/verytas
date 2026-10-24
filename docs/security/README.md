# Security review

Verytas holds unreleased campaigns, confidential product names and the brand's own artwork, so we had
it audited before Round 2 and fixed what the audit found. This page is the result: what was checked,
what was found, the commit that fixed each item, and what is still open. It also covers a review of the
live demo and of the vision worker added since.

## How it was reviewed

| | |
|---|---|
| Method | The [security-audit skill](https://github.com/cloudflare/security-audit-skill) published by Cloudflare: reconnaissance, parallel hunters per attack surface, independent verifiers, then a coverage critic |
| Code reviewed | `33ceccd` on `dev`, 22 October 2026 |
| Scope | `backend/verytas`, `web/src`, `deploy`, `.github/workflows`, `blackbox` |
| Profile | `quick`: one hunter wave and one coverage critic, 24 agent runs in all |
| Execution | Source review only. No code was run against the live demo and nothing was sent over the network. |

A quick profile is a partial pass by design. Its gaps are listed under [Not yet covered](#not-yet-covered).

## Confirmed findings

Both confirmed findings are low severity, and both are fixed with regression tests in
[`backend/tests/test_audit_fixes.py`](../../backend/tests/test_audit_fixes.py).

| Severity | Finding | Fix | Fixed in |
|---|---|---|---|
| Low | The read-only auditor role could post comments | Comments need a writer role (creator, reviewer, approver, admin) | [`cad2338`](https://github.com/varadarajjborkar/verytas/commit/cad2338) |
| Low | The audit log showed confidential rule codes, asset names and notes to a lower-clearance auditor | Each entry is checked against the tier of the object it is about, when the log is read; confidential-term entries are shown to brand admins only; paging reads past hidden entries | [`e1d5ffa`](https://github.com/varadarajjborkar/verytas/commit/e1d5ffa), [`4344642`](https://github.com/varadarajjborkar/verytas/commit/4344642) |

## Leads the audit could not prove, and what we did

The audit also lists leads it traced but could not confirm without running code. We treated each one as real.

| Lead | What we changed | Fixed in |
|---|---|---|
| The edge worker could be made to fetch another host's content (`//host` paths) | The upstream URL is built from a fixed origin, and redirects are rewritten only when they point back at it | [`c664631`](https://github.com/varadarajjborkar/verytas/commit/c664631) |
| Ask Verytas could render an image from any URL a model chose | A Content Security Policy keeps images on this origin (`img-src 'self' data: blob:`), with `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'` and `form-action 'self'` | [`d944579`](https://github.com/varadarajjborkar/verytas/commit/d944579) |
| Re-disputing findings could raise a rule's threshold for the whole workspace | Threshold learning counts each finding once and only its latest decision | [`cad2338`](https://github.com/varadarajjborkar/verytas/commit/cad2338) |
| The session cookie could be set by a sibling host on the shared `sslip.io` name | The cookie is `__Host-` prefixed in production, and sign-out clears it with the same attributes | [`d944579`](https://github.com/varadarajjborkar/verytas/commit/d944579), [`0a7e1f8`](https://github.com/varadarajjborkar/verytas/commit/0a7e1f8) |
| The PDF active-content scan was quadratic on unterminated streams | A linear scan, and upload metrics run on their own threads with a 30 s deadline | [`e280e53`](https://github.com/varadarajjborkar/verytas/commit/e280e53), [`4344642`](https://github.com/varadarajjborkar/verytas/commit/4344642) |
| Uploads had no quota and were never cleaned up | 1 GB per person and 10 GB per workspace by default; uploads no version uses are deleted after a day by an hourly sweep, and before a quota refusal | [`3fe9799`](https://github.com/varadarajjborkar/verytas/commit/3fe9799) |
| Reviews had no concurrency cap, and loaded attachments before waiting | At most four reviews run at once, and a review takes its slot before it loads any file | [`3a22d74`](https://github.com/varadarajjborkar/verytas/commit/3a22d74) |
| The server re-resolved backend dependencies, so it did not run what CI tested | Hashed lock files, installed with `pip --require-hashes` in CI and on deploy; `pip-audit` checks the same lock | [`69f256b`](https://github.com/varadarajjborkar/verytas/commit/69f256b) |
| The running services could write the cache the deploy build reads | Build caches live under a directory the services cannot write | [`0b28062`](https://github.com/varadarajjborkar/verytas/commit/0b28062) |

One more candidate was found by the audit's lead and not independently verified: an approval could pass
on the previous version's review in the moment between a new version being saved and its review being
created. We fixed it anyway: approval now requires the newest review to be for the newest version
([`cad2338`](https://github.com/varadarajjborkar/verytas/commit/cad2338)).

## Review of the live demo

On 23 October 2026 we checked the deployed demo the way anyone on the internet could reach it: read-only
requests to [verytas.pages.dev](https://verytas.pages.dev), first signed out, then signed in through the
demo picker as a creator. Nothing was flooded and nothing was changed.

| Check | Result |
|---|---|
| Common leak paths (`.env`, `.git/config`, `package.json`, `openapi.json`, `/docs`, path traversal) | Nothing served: every path redirects to sign-in, and the API itself is not reachable from outside (it listens on the server's loopback) |
| Signed out, the API proxy | `401` |
| Signed in as a creator: rules, confidential terms, brand assets, creator insights | Refused with the role each needs (`403`) |
| A creator opening the other creators' pieces (ids 1 to 40) | None readable; only their own |
| Audit log, account creation, bootstrap | Not forwarded by the web server at all (`404`) |
| A write from another site's origin | Refused (`403 cross-site request refused`) |
| Malformed and invalid input | Validation errors only; no stack traces or internal paths |
| Session cookie | `__Host-` prefixed, `HttpOnly`, `Secure`, `SameSite=Strict` |
| The JavaScript the browser downloads (12 bundles) | No keys, tokens or environment names; no source maps published |
| Response headers | HSTS, `nosniff`, `X-Frame-Options: DENY`, referrer policy and a partial CSP were present |

Two things were fixed in [`ab10825`](https://github.com/varadarajjborkar/verytas/commit/ab10825):

| Finding | Fix |
|---|---|
| `Permissions-Policy` denied the microphone to every origin, ours included, so the creator's spoken brief could not record | Allowed for this site only: `microphone=(self)` |
| Responses announced `X-Powered-By: Next.js` | Turned off |

## The vision worker

The worker that finds redrawn mascots runs on its own instance and was reviewed before it went live
(internal review findings 251 to 302, all fixed). How it is kept safe:

| Concern | How it is handled |
|---|---|
| Who can call it | Only the API server: its security group admits port 8100 from the API server's group alone, and every request carries a token compared in constant time, checked before the body is read |
| Hostile images | Only PNG, JPEG and WebP are decoded; size, side and pixel-count limits, and decompression bombs refused (`413`) |
| Secrets | The token and a read-only GitHub deploy key live in SSM Parameter Store, read through the instance's own role; the key is root-only and hidden from the worker process |
| What the instance may do | Its role can read only its two parameters. The API server's role can only start instances tagged `verytas-vision`. Both roles are new and scoped to this |
| Code it runs | Pulled from GitHub at boot with a pinned host key, installed from a hash-pinned lock; model files pinned by SHA-256 and Hugging Face models by commit |
| Restricted artwork | Named only by number in anything a reviewer can read |
| Plain http | Refused unless the worker is on this machine or the private network |
| Cost | It stops itself after 20 idle minutes, even if the worker never starts; the AWS budget's automatic stop covers it too |

## Uploaded documents and their previews

Review now reads PowerPoint, Excel and HTML as well as PDF and Word, and shows any attached document as it
looks. Each step was checked by our own error-check passes (internal findings 466 to 503, all fixed, each
with a test), with these results:

| Concern | How it is handled |
|---|---|
| Zip and XML bombs | Office files are read within an unzipped-size budget (40 MB, 5,000 entries) checked before anything is read; XML is parsed with entities, DTDs and network access off; HTML is capped at 5 MB |
| A file that pulls in something from elsewhere | Never fetched by the readers. For conversion, every reference to anything outside the file is cut from a parsed copy: relationships (any quoting, entities or attribute order, and any URL target), field codes that pull in pictures or text (read whole, however Word split them across runs), imported HTML chunks and embedded packages |
| LibreOffice reading hostile files | Runs only in `verytas-convert@.service`, started per file from a socket only the API's user can open: a user created for that run, no network (`PrivateNetwork`), no view of `/srv/verytas`, `/root` or `/etc/ssh`, no capabilities or new privileges, memory, task, CPU and 120 s limits, a fresh profile with macros off and every internet setting pointed at a closed port. Checked on the server: a Word file asking for the API's secrets file and a URL converted with neither |
| A web page shown to a reviewer | Never served as a page by the API (it comes back as text in JSON). The browser shows it in an `iframe` with an empty sandbox and a deny-all content policy (`default-src 'none'; img-src data:`), after scripts, frames, templates, SVG animation, every attribute that can carry an outside address and any style that could fetch are removed. A deliberately hostile page made no request outside the console |
| Who can see a preview | The same check as the piece itself: one `404` for a missing piece, one above the reader's clearance and another creator's; files are looked up within the piece's workspace |
| Slow or stuck conversions | One at a time, with their own threads apart from the rest of the API; a request waits at most a minute for its turn, and the converter's whole process group is killed at its deadline |

## The chat assistants' instructions

Asked "give me your prompt", Ask Verytas once wrote out its system prompt on the live demo. Nothing private
was in it: workspace data is filtered to the reader's clearance and redacted before a model sees it. But a
model that recites its rules hands anyone a map of what to argue around. Both chats (Ask Verytas and the
Summarize chat) now go through `web/src/lib/guard.ts`
([`0d6d84d`](https://github.com/varadarajjborkar/verytas/commit/0d6d84d)).

| Layer | What it does |
|---|---|
| The question | A request for the assistant's own set-up ("your prompt", "the text before my first message", "ignore your previous instructions") gets a fixed answer, and the model is not called. The patterns name the assistant's set-up only, so "show me the logo usage instructions" or "the creator's original message" still reach the model. |
| The answer | The reply is streamed with its last 260 characters held back. Once it quotes 30 words of the instructions (counted as words covered by 8-word runs), the rest is dropped and the fixed answer goes instead, before any of the quote is sent. For Ask Verytas this includes the prose of the chart library's prompt, which the model once reached for. |
| The rules | Both prompts tell the model its instructions are not data and are never repeated, summarised or translated. |

Tested with 7 reworded attacks against the running app, and offline with 11 attack phrasings and 14
ordinary questions (among them "copy the prompt used for this image" and "is the hidden message in the
caption a problem?"): every attack refused, every ordinary question answered. A model paraphrasing its rules in its own words is not caught by the second layer; the
third covers that, and nothing secret is in the prompts to begin with.

## Confidential terms said in part

A codename on the terms list as "Project Falcon" was hidden only when written in full, so "Falcon was named
in the interview" reached the model. Every guard that keeps a term from leaving (model egress, image text,
rewrites) now also hides the distinctive name after a generic lead word (project, codename, operation,
programme, program, initiative), when it is at least four letters, as a whole word starting with a capital:
"Falcon" and "FALCON" are hidden, while "falcons fly", "restart" and "what is next?" are left alone
([`2f2fbcf`](https://github.com/varadarajjborkar/verytas/commit/2f2fbcf)). The CONF-LEAK finding still needs the
full term, so a must-fix is not raised on every "falcon".

## Before the repository went public

The full history (305 commits, every branch) was scanned with gitleaks 8.30 on 25 October 2026: no
findings. A second pass looked for files that should never be committed (`.env`, keys, certificates, the
demo account file) and for key assignments in every added line: none. Keys live only in files git ignores
and, on the server, in `/srv/verytas/etc`.

## Hardening notes

The audit's hardening suggestions, and where each one stands.

| Note | Status |
|---|---|
| Content Security Policy | Done for images, objects, base URI, framing and forms. A nonce-based `script-src` is still to do. |
| Framework disclosure in headers | Done ([`ab10825`](https://github.com/varadarajjborkar/verytas/commit/ab10825)) |
| `/contents/precheck` should need a writer role | Done ([`ce12803`](https://github.com/varadarajjborkar/verytas/commit/ce12803)) |
| Upload metrics should have a deadline | Done ([`4344642`](https://github.com/varadarajjborkar/verytas/commit/4344642)). The precheck itself still has none. |
| Learned thresholds counted repeated decisions | Done ([`cad2338`](https://github.com/varadarajjborkar/verytas/commit/cad2338)) |
| Edge worker should compare redirect origins | Done ([`c664631`](https://github.com/varadarajjborkar/verytas/commit/c664631)). Allowlisting forwarded headers is still to do. |
| Fail closed when sign-in is off in production | Open. The deployed demo runs with sign-in on, so this only matters for a misconfigured install. |
| Tokens never expire and sign-out does not revoke them | Partly done. A password account's token lapses 7 days after sign-in (`account_token_days`) and sign-out revokes it at the API. Tokens an admin issues, and the shared demo picker's, still never lapse: they have no password to get a new one with. Short access tokens with rotating refresh tokens are still to do. |
| No per-user rate or spend limit on Ask Verytas | Open |
| `Redactor.restore` also restores placeholders a user typed | Open |
| The audit chain's head is not anchored or signed; signing keys share an owner with the database | Open |
| All server jobs share one user; the deploy and reset units are unconfined | Partly: document conversion runs in its own sandboxed service as a per-run user (above). The API, web, deploy and reset jobs still share one user, and the deploy and reset units are still unconfined. |
| The `live` branch can be pushed directly; pnpm, `pip-audit` and the Whisper model revision are not pinned by hash | Open |
| Chat storage and some colour fields have no size ceiling | Open |
| Uploads are scoped to the workspace, not to their owner or piece | Partly: quotas are per person, access is still per workspace |

## Not yet covered

The audit's coverage critic deferred six areas to a deeper run:

1. Admin ingest and brand-asset matching (`assets.py`, `pixels.py`, `ocr.py` and the brand-book parsers).
2. Regular expressions that could be slow on hostile input in text checks and ingest.
3. The model suggestion pipeline behind apply-fixes, AI edit and resubmit.
4. Cloudflare edge caching of private responses.
5. `Redactor.restore` with user-typed placeholders.
6. Server-rendered pages and library helpers, including the demo-data fallback.

The next run should use the `standard` profile in a sandbox, starting from these.

## What held up

- **Access control:** creators see only their own pieces, tier checks apply on every read, and the web
  server forwards only an allowlisted set of API routes.
- **Credentials:** tokens are random, stored only as SHA-256 hashes and looked up by hash.
- **Findings and audit log:** findings carry Ed25519 signatures; audit entries are hash-chained and
  appended one at a time.
- **Uploads:** file types are sniffed from their bytes, images are size-checked before decoding, and Word,
  PowerPoint and Excel files are parsed with entities, DTDs and network access turned off.
- **Rendering:** no raw HTML from a model is rendered, and the only link a model answer can open is http(s).
  An uploaded web page is shown only in the locked frame described above.
- **Cross-site requests:** `SameSite=Strict` cookies, Origin checks and JSON-only sign-in.
- **CI and deploy:** actions pinned to commit hashes, a read-only default token, a checksummed secret
  scanner, and a read-only deploy key with a pinned host key.

## Updating the dependency lock

After changing `backend/pyproject.toml`, regenerate both locks from the `backend` folder, then run the
tests on them:

```bash
uv pip compile pyproject.toml requirements-build.in --universal --python-version 3.12 \
  --generate-hashes --no-header -o requirements.lock
uv pip compile pyproject.toml requirements-build.in --extra dev --universal --python-version 3.12 \
  --generate-hashes --no-header -o requirements-dev.lock
```

The vision worker has its own lock, for Linux on ARM, where it runs:

```bash
uv pip compile requirements-vision.in --python-platform aarch64-unknown-linux-gnu --python-version 3.12 \
  --generate-hashes --no-header -o requirements-vision.lock
```
