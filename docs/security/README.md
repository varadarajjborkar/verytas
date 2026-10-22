# Security review

Verytas holds unreleased campaigns, confidential product names and the brand's own artwork, so we had
it audited before Round 2 and fixed what the audit found. This page is the result: what was checked,
what was found, the commit that fixed each item, and what is still open.

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

## Hardening notes

The audit's hardening suggestions, and where each one stands.

| Note | Status |
|---|---|
| Content Security Policy | Done for images, objects, base URI, framing and forms. A nonce-based `script-src` is still to do. |
| `/contents/precheck` should need a writer role | Done ([`ce12803`](https://github.com/varadarajjborkar/verytas/commit/ce12803)) |
| Upload metrics should have a deadline | Done ([`4344642`](https://github.com/varadarajjborkar/verytas/commit/4344642)). The precheck itself still has none. |
| Learned thresholds counted repeated decisions | Done ([`cad2338`](https://github.com/varadarajjborkar/verytas/commit/cad2338)) |
| Edge worker should compare redirect origins | Done ([`c664631`](https://github.com/varadarajjborkar/verytas/commit/c664631)). Allowlisting forwarded headers is still to do. |
| Fail closed when sign-in is off in production | Open. The deployed demo runs with sign-in on, so this only matters for a misconfigured install. |
| Tokens never expire and sign-out does not revoke them | Open |
| No per-user rate or spend limit on Ask Verytas | Open |
| `Redactor.restore` also restores placeholders a user typed | Open |
| The audit chain's head is not anchored or signed; signing keys share an owner with the database | Open |
| All server jobs share one user; the deploy and reset units are unconfined | Open |
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
- **Uploads:** file types are sniffed from their bytes, images are size-checked before decoding, and Word
  files are parsed with entities, DTDs and network access turned off.
- **Rendering:** no raw HTML is rendered, and the only link a model answer can open is http(s).
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
