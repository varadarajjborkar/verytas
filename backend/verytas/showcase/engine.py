"""Seeds the demo companies through the real API (offline models) on a simulated clock.

Every review, decision, escalation and timeline entry is genuine and has a believable age. Each company is its
own workspace in the same database: the first through /bootstrap, the others created in-process (bootstrap is
for the first workspace only) and then driven through the API with their own admin token. Tokens are written
to the env and accounts files, never printed."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from verytas.showcase import spec
from verytas.showcase.spec import NOW, TODAY, Company, Piece, at

COMPANY_MODULES = ("kitepath", "paisaloop", "nutmeg", "dewlight")


class _Clock(datetime):
    """Stands in for datetime inside verytas.models, so `utcnow()` reads the simulated time."""

    at: datetime = NOW

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return cls.at if tz is not None else cls.at.replace(tzinfo=None)


def load(only: list[str] | None = None) -> list[Company]:
    out = []
    for name in COMPANY_MODULES:
        if only and name not in only:
            continue
        if importlib.util.find_spec(f"verytas.showcase.{name}") is None:
            print(f"seed: no module for company '{name}'; skipped")
            continue
        out.append(importlib.import_module(f"verytas.showcase.{name}").build())
    unknown = sorted(set(only or ()) - set(COMPANY_MODULES))
    if unknown or not out:
        raise SystemExit(f"seed: unknown or missing companies: {', '.join(unknown) or 'none found'}; "
                         f"known: {', '.join(COMPANY_MODULES)}")
    return out


def _token_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in seen]
    path.write_text("\n".join(out) + "\n")


def _demo_accounts(path: Path, runs: list[tuple[Company, dict[str, str]]]) -> None:
    """The demo sign-in page's accounts, with their tokens: a server-side file, never sent to a browser.
    Top-level `brand`, `seeded_at` and `people` are the first company's, as the web has always read them;
    `companies` lists every company with its own people."""
    seeded = datetime.now(UTC).replace(microsecond=0)
    names = lambda co: {m.key: m.name for m in [*co.team, *co.creators]}  # noqa: E731

    def people(co: Company, tok: dict[str, str]) -> list[dict]:
        n = names(co)
        return [{"key": jk, "name": n[mk], "side": side, "title": title, "blurb": blurb, "token": tok[mk]}
                for jk, mk, side, title, blurb in co.demo]

    first, first_tok = runs[0]
    doc = {"brand": first.brand, "seeded_at": seeded.isoformat(), "people": people(first, first_tok),
           "companies": [{"brand": co.brand, "industry": co.industry, "people": people(co, tok)}
                         for co, tok in runs]}
    # Created owner-only from the start: written first and narrowed after, the tokens would sit readable
    # for a moment, and a file left over from an earlier run keeps its mode through a plain rewrite.
    path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(doc, indent=2))


def seed(db_path: Path, keys_dir: Path, env_out: Path | None, demo_out: Path | None = None, *,
         companies: list[str] | None = None, limit: int | None = None) -> dict:
    """`companies` and `limit` (pieces per company) make a small seed for tests; the CLI seeds everything."""
    from verytas import models
    from verytas.config import Settings
    from verytas.main import create_app

    if db_path.exists():
        raise SystemExit(f"{db_path} exists; pick a new path so nothing is overwritten")
    settings = Settings(database_url=f"sqlite+aiosqlite:///{db_path}", llm_mode="offline", keys_dir=keys_dir)
    models.datetime = _Clock  # utcnow() now reads the simulated clock
    counts: dict = {"pieces": 0, "escalations": 0, "decisions": 0, "companies": {}}
    runs: list[tuple[Company, dict[str, str]]] = []
    try:
        with TestClient(create_app(settings)) as c:
            chosen = load(companies)
            for i, co in enumerate(chosen):
                started = time.monotonic()
                tok, got = _seed_company(c, co, first=i == 0, limit=limit)
                # A full seed runs for many minutes on a small server; a line per company tells a
                # watcher it is moving and which brand ate the time.
                print(f"seed: {co.brand} ({i + 1}/{len(chosen)}): {got.get('pieces', 0)} pieces in "
                      f"{time.monotonic() - started:.0f} s", file=sys.stderr, flush=True)
                runs.append((co, tok))
                counts["companies"][co.brand] = got
                for k in ("pieces", "escalations", "decisions"):
                    counts[k] += got.get(k, 0)
            _Clock.at = NOW
            if env_out is not None:
                first, tok = runs[0]
                creator = next(k for k in tok if k == "dev") if "dev" in tok else first.creators[0].key
                _token_env(env_out, {"VERYTAS_API_TOKEN": tok["admin"], "VERYTAS_CREATOR_TOKEN": tok[creator]})
            if demo_out is not None:
                _demo_accounts(demo_out, runs)
    finally:
        models.datetime = datetime
    return counts


def _seed_company(c: TestClient, co: Company, *, first: bool, limit: int | None) -> tuple[dict[str, str], dict]:
    from verytas.services.workspace import create_workspace

    got: dict = {"pieces": 0, "escalations": 0, "decisions": 0, "disputes": 0, "comments": 0}
    _Clock.at = at(co.days)
    head = co.team[0]  # keys "admin", "approver" and "reviewer" are what piece flows and the sign-in file use
    if first:
        boot = c.post("/bootstrap", json={"workspace_name": co.brand, "admin_email": head.email,
                                          "admin_name": head.name})
        boot.raise_for_status()
        admin_token = boot.json()["token"]
    else:
        db = c.app.state.db

        async def make() -> str:
            async with db.sessionmaker() as session:
                _, _, token = await create_workspace(session, name=co.brand, admin_email=head.email,
                                                     admin_name=head.name)
                await session.commit()
                return token

        admin_token = c.portal.call(make)
    tok = {"admin": admin_token}
    h = lambda who: {"Authorization": f"Bearer {tok[who]}"}  # noqa: E731
    for m in [*co.team[1:], *co.creators]:
        r = c.post("/users", headers=h("admin"), json={"email": m.email, "name": m.name, "role": m.role,
                                                       "clearance": "internal"})
        r.raise_for_status()
        tok[m.key] = r.json()["token"]

    def post(path: str, who: str, body: dict, params: dict | None = None):
        r = c.post(path, headers=h(who), json=body, params=params)
        r.raise_for_status()
        return r.json()

    rule_ids: dict[str, int] = {}
    for rule in co.rules:
        rid = post("/rules", "admin", {**{"tier": "public"}, **rule})["id"]
        c.patch(f"/rules/{rid}", headers=h("admin"), json={"status": "active"}).raise_for_status()
        rule_ids[rule["code"]] = rid
    fact_ids: dict[str, int] = {}
    for f in co.facts:
        body = {k: v for k, v in f.items() if k not in ("key", "supersedes", "from", "to")}
        body["valid_from"] = str(_date(f["from"]))
        if f.get("to") is not None:
            body["valid_to"] = str(_date(f["to"]))
        if f.get("supersedes"):
            body["supersedes_id"] = fact_ids[f["supersedes"]]
        fact_ids[f.get("key", f["statement"])] = post("/facts", "admin", {"tier": "public", **body})["id"]
    for t in co.terms:
        body = {"term": t["term"], "note": t.get("note")}
        if t.get("embargo") is not None:
            body["embargo_until"] = str(_date(t["embargo"]))
        post("/confidential-terms", "admin", body)
    for ct in co.contacts:
        post("/public-contacts", "admin", ct)
    for art in co.assets:
        body = {k: v for k, v in art.items() if k != "image"}
        post("/brand-assets", "admin", {**body, "data_base64": _b64(art["image"]())})
    got["assets"] = len(co.assets)

    events: dict[str, int] = {}
    actions: list[tuple[datetime, int, Callable[[], None]]] = []
    seq = 0

    def add(when: datetime, fn: Callable[[], None]) -> None:
        nonlocal seq
        seq += 1
        if when <= NOW:  # a step that hasn't happened yet isn't part of the history
            actions.append((when, seq, fn))

    def make_event(e: dict) -> Callable[[], None]:
        def run() -> None:
            body = {k: v for k, v in e.items() if k not in ("key", "created", "start", "end")}
            body["starts_on"] = str(_date(e["start"]))
            if e.get("end") is not None:
                body["ends_on"] = str(_date(e["end"]))
            events[e["key"]] = post("/events", "admin", body)["id"]
        return run

    for e in co.events:
        add(at(e["created"]), make_event(e))
    got["events"] = len(co.events)

    def make_person(p: dict) -> Callable[[], None]:
        def run() -> None:
            body = {k: v for k, v in p.items() if k not in ("from", "to", "events")}
            body["valid_from"] = str(_date(p["from"]))
            if p.get("to") is not None:
                body["valid_to"] = str(_date(p["to"]))
            body["event_ids"] = [events[k] for k in p.get("events", []) if k in events]
            post("/people", "admin", body)
        return run

    for p in co.people:
        last = max((e["created"] for e in co.events if e["key"] in p.get("events", [])), default=co.days)
        add(at(min(last, co.days) - 0.01), make_person(p))
    got["people"] = len(co.people)

    for days_ago, kind, args in co.admin_log:
        add(at(days_ago), _admin_step(c, h, kind, args, rule_ids, fact_ids))

    state: dict[str, dict] = {}
    pieces = co.pieces()
    if limit is not None and limit < len(pieces):
        # Spread over the whole list: stories are written in calendar order, so the first N would keep
        # the quiet early weeks and drop the launch and festival stories at the end.
        pieces = [pieces[i * len(pieces) // limit] for i in range(limit)]
    for p in pieces:
        born = at(p.days_ago)
        who = p.who

        def create(p=p, who=who) -> None:
            payload = {"title": p.title, "channel": p.channel, "body": p.body, "tier": "public"}
            if p.event and p.event in events:
                payload["event_id"] = events[p.event]
            if p.images or p.colors:
                payload["attachments"] = {"images": p.images() if p.images else [], "colors": p.colors or []}
            if p.notes:
                payload["creator_notes"] = p.notes
            r = c.post("/contents?wait=true", headers=h(who), json=payload)
            r.raise_for_status()
            state[p.key] = {"id": r.json()["content"]["id"], "review": r.json()["review_id"], "who": who, "p": p}
            got["pieces"] += 1

        add(born, create)
        for hours, act, args in p.flow:
            add(born + timedelta(hours=hours), _step(c, h, state, p.key, act, args, got, co))
        for key, hours, code, by, act, reason, note in co.decisions:
            if key == p.key:
                add(born + timedelta(hours=hours), _step(c, h, state, key, "decide", {
                    "rule": code, "by": by, "action": act, "reason_code": reason, "reason_text": note}, got, co))
    for when, _, run in sorted(actions, key=lambda a: (a[0], a[1])):
        _Clock.at = when
        run()
    return tok, got


def _date(v: int | str | date) -> date:
    """Days from today (negative: in the past) or an ISO date."""
    if isinstance(v, int):
        return TODAY + timedelta(days=v)
    return date.fromisoformat(v) if isinstance(v, str) else v


def _b64(img) -> str:
    from verytas.showcase.art import b64

    return b64(img)


def _admin_step(c, h, kind: str, args: dict, rule_ids: dict, fact_ids: dict) -> Callable[[], None]:
    def run() -> None:
        if kind == "patch_rule":
            c.patch(f"/rules/{rule_ids[args['code']]}", headers=h("admin"), json=args["patch"]).raise_for_status()
        elif kind == "retire_fact":
            c.post(f"/facts/{fact_ids[args['key']]}/retire", headers=h("admin")).raise_for_status()
        elif kind == "new_fact":
            body = {k: v for k, v in args.items() if k not in ("key", "supersedes", "from", "to")}
            body["valid_from"] = str(_date(args["from"]))
            if args.get("supersedes"):
                body["supersedes_id"] = fact_ids[args["supersedes"]]
            r = c.post("/facts", headers=h("admin"), json={"tier": "public", **body})
            r.raise_for_status()
            fact_ids[args.get("key", args["statement"])] = r.json()["id"]
    return run


def _finding_for(findings: list[dict], rule: str | None) -> dict | None:
    if rule:
        return next((f for f in findings if any(x["kind"] == "rule" and x["label"].startswith(rule + " ")
                                                for x in f["citations"])), None)
    return next((f for f in findings if f["level"] == "blocker"), findings[0] if findings else None)


def _settled(call: Callable[[], Any], tries: int = 120) -> Any:
    """The response once no automated review is still running for the piece.

    Creating an event starts background re-reviews of pieces in flight, and an approval that lands
    before one finishes is refused ("the latest automated review has not finished"), which no override
    can pass. A manager would wait; so does the seed, up to a minute."""
    for _ in range(tries):
        r = call()
        if r.status_code != 409 or "has not finished" not in r.text:
            return r
        time.sleep(0.5)
    return r


def _step(c, h, state, key: str, act: str, args: dict, got: dict, co: Company) -> Callable[[], None]:
    def run() -> None:
        s = state.get(key)
        if s is None:
            return
        cid, who = s["id"], s["who"]
        if act == "send":
            c.post(f"/contents/{cid}/transition", headers=h(who), json={"to": "in_review"}).raise_for_status()
        elif act == "back":
            c.post(f"/contents/{cid}/transition", headers=h(args.get("by", "approver")),
                   json={"to": "changes_requested", "note": args["note"]}).raise_for_status()
        elif act in ("approve", "publish"):
            to = "approved" if act == "approve" else "published"
            r = _settled(lambda: c.post(f"/contents/{cid}/transition", headers=h("approver"), json={"to": to}))
            if r.status_code == 409:  # open blockers or unchecked parts: the manager goes ahead with a reason
                r = c.post(f"/contents/{cid}/transition", headers=h("approver"), json={
                    "to": to, "override_blockers": True,
                    "note": args.get("note", "Checked by hand: the flagged parts were reviewed and are fine to "
                                              "publish.")})
            r.raise_for_status()
        elif act == "withdraw":
            c.post(f"/contents/{cid}/transition", headers=h(who), json={"to": "withdrawn"}).raise_for_status()
        elif act == "fix":
            payload = {"body": args["body"]}
            if s["p"].fix_images or s["p"].fix_colors:
                payload["attachments"] = {"images": s["p"].fix_images() if s["p"].fix_images else [],
                                          "colors": s["p"].fix_colors or []}
            r = c.post(f"/contents/{cid}/versions?wait=true", headers=h(who), json=payload)
            r.raise_for_status()
            s["review"] = r.json()["review_id"]
        elif act == "applyfix":
            findings = c.get(f"/reviews/{s['review']}", headers=h(who)).json()["findings"]
            ids = [f["id"] for f in findings if f["suggestions"] and f["source"] == "body"]
            r = c.post(f"/contents/{cid}/resubmit?wait=true", headers=h(who), json={"apply": ids})
            r.raise_for_status()
            s["review"] = r.json()["submit"]["review_id"]
        elif act == "decide":
            findings = c.get(f"/reviews/{s['review']}", headers=h(args["by"])).json()["findings"]
            target = _finding_for(findings, args["rule"])
            if target is not None:
                c.post(f"/findings/{target['id']}/decision", headers=h(args["by"]), json={
                    "action": args["action"], "reason_code": args["reason_code"],
                    "reason_text": args["reason_text"]}).raise_for_status()
                got["decisions"] += 1
            else:
                # The script expected a finding this review didn't raise: say so, so data and checks
                # drifting apart shows up in the seed log instead of as a quietly thinner demo.
                print(f"seed: {co.brand} {key}: no {args['rule']} finding to decide on; skipped",
                      file=sys.stderr, flush=True)
        elif act == "autodecide":
            _autodecide(c, h, s, key, args["by"], got, co)
        elif act == "comment":
            c.post(f"/contents/{cid}/comments", headers=h(args.get("by", "reviewer")),
                   json={"body": args["body"]}).raise_for_status()
            got["comments"] += 1
        elif act == "resolve":
            esc = c.get("/escalations", headers=h("approver"), params={"content_id": cid}).json()
            if esc:
                c.post(f"/escalations/{esc[0]['id']}/resolve", headers=h(args.get("by", "approver")),
                       json={k: v for k, v in args.items() if k != "by"}).raise_for_status()
        elif act == "escalate":
            findings = c.get(f"/reviews/{s['review']}", headers=h(who)).json()["findings"]
            target = _finding_for(findings, args.get("rule"))
            if target is not None:
                c.post(f"/findings/{target['id']}/escalations", headers=h(who),
                       json={"message": args["message"]}).raise_for_status()
                got["escalations"] += 1
        elif act == "dispute":
            findings = c.get(f"/reviews/{s['review']}", headers=h(who)).json()["findings"]
            target = _finding_for(findings, args.get("rule"))
            if target is not None:
                r = c.post(f"/findings/{target['id']}/disputes", headers=h(who), params={"wait": "true"},
                           json={"claim": args["claim"], "language": args.get("language")})
                r.raise_for_status()
                got["disputes"] += 1
            else:
                print(f"seed: {co.brand} {key}: no {args.get('rule')} finding to dispute; skipped", file=sys.stderr,
                      flush=True)
    return run


def _autodecide(c, h, s: dict, key: str, by: str, got: dict, co: Company) -> None:
    """A reviewer works through the findings of a piece the way their record says they do: most are acted on,
    some skipped, and the same rule is upheld by one reviewer and overridden by another. Only an approver may
    dismiss a must-fix finding, so a reviewer upholds those."""
    findings = c.get(f"/reviews/{s['review']}", headers=h(by)).json()["findings"]
    stance = co.stance.get(by, {})
    for f in findings:
        code = next((x["label"].split(" ")[0] for x in f["citations"] if x["kind"] == "rule"), None)
        if code is None or f["decisions"]:
            continue
        rng = random.Random(f"{co.key}:{key}:{by}:{code}:{f['quote']}")
        if rng.random() > 0.85:
            continue
        p_accept, reasons = stance.get(code) or stance.get("*") or (0.75, [("false_positive", "Not what the rule "
                                                                                              "means here.")])
        if (f["level"] == "blocker" and by != "approver") or rng.random() < p_accept:
            body = {"action": "accepted"}
        else:
            reason, note = (reasons or [("false_positive", "Reads fine to me.")])[rng.randrange(len(reasons) or 1)]
            body = {"action": "rejected", "reason_code": reason, "reason_text": note}
        c.post(f"/findings/{f['id']}/decision", headers=h(by), json=body).raise_for_status()
        got["decisions"] += 1


__all__ = ["seed", "load", "Piece", "spec"]
