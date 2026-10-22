"""Campaign loop: realities -> templates -> filled cases -> reviews -> grades -> learning.

For each reality a fresh Verytas server is started and set up through the API
the way a brand admin would. Each generation fills every template several
times, choosing variants with the bandit, so a campaign drifts towards what
the system under test gets wrong. In LLM mode an adversary step also invents
new spellings for the terms that slipped through, and those become new arms.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from blackbox.client import Api, Server, ServerError
from blackbox.content import SLOT, Template, llm_templates, offline_templates
from blackbox.llm import OllamaChat, load_key
from blackbox.oracle import grade
from blackbox.plants import (
    APPENDED,
    Plant,
    appended_plant,
    arms_for,
    attachment_plant,
    casing_plant,
    stat_plant,
    term_plant,
)
from blackbox.store import Store
from blackbox.world import Reality, llm_reality, offline_reality


@dataclass
class Config:
    realities: int = 2
    templates: int = 6
    fills: int = 4
    generations: int = 2
    gen: str = "offline"  # offline | llm
    review: str = "offline"  # offline | live
    seed: int = 7
    concurrency: int = 8
    gate_checks: bool = True
    adversary: bool = True
    review_timeout_s: float = 180.0
    world_model: str = "gpt-oss:120b"
    gen_model: str = "gpt-oss:20b"


@dataclass
class Case:
    case_id: str
    template: Template
    body: str
    plants: list[Plant]
    attachments: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: {"images": [], "colors": []})


# --- setting a reality up through the API ---------------------------------------------------------

async def load_reality(api: Api, reality: Reality) -> dict[str, str]:
    spec = reality.spec
    slug = re.sub(r"[^a-z0-9]+", "", spec.name.lower()) or "brand"
    admin = await api.ok("POST", "/bootstrap", json={"workspace_name": spec.name,
                                                     "admin_email": f"admin@{slug}.example.com",
                                                     "admin_name": "Sim Admin"})
    api.auth(admin["token"])

    terms = list(spec.banned)
    half = max(1, len(terms) // 2)
    # Rules and facts are published as "public" so they apply to public content;
    # the content under test is public social copy.
    rules = [
        {"code": "SIM-BANNED", "category": "terminology", "kind": "deterministic", "severity": "must",
         "title": "Banned phrases", "text": "Never use: " + ", ".join(terms[:half]),
         "pattern": {"type": "banned_terms", "terms": terms[:half]}},
        {"code": "SIM-PREFERRED", "category": "terminology", "kind": "deterministic", "severity": "should",
         "title": "Preferred wording", "text": "; ".join(f"say '{spec.banned[t]}' not '{t}'" for t in terms[half:]),
         "pattern": {"type": "preferred_terms", "map": {t: spec.banned[t] for t in terms[half:]}}},
        {"code": "SIM-CASING", "category": "terminology", "kind": "deterministic", "severity": "should",
         "title": "Brand name casing", "text": f"Always write the brand as {spec.name}.",
         "pattern": {"type": "casing", "terms": [spec.name]}},
        {"code": "SIM-VOICE", "category": "tone", "kind": "semantic", "severity": "should",
         "title": "Brand voice", "text": f"Sound {spec.voice}. No hype, no put-downs.",
         "good_examples": spec.plain_examples, "bad_examples": spec.hype_examples, "pattern": {}},
    ]
    if not terms[half:]:
        rules.pop(1)
    for r in rules:
        created = await api.ok("POST", "/rules", json={**r, "tier": "public", "source_ref": "Brand book v3"})
        # New rules start as drafts awaiting approval; the admin publishes them.
        if created.get("status") != "active":
            await api.ok("PATCH", f"/rules/{created['id']}", json={"status": "active"})

    for stat in spec.stats:
        old = await api.ok("POST", "/facts", json={
            "statement": f"{stat.old_value} {stat.subject}", "value": stat.old_value, "unit": stat.unit,
            "subject": stat.subject, "source_ref": "Metrics report 2024", "tier": "public",
            "valid_from": "2023-01-01", "valid_to": reality.change_date.isoformat()})
        new = await api.ok("POST", "/facts", json={
            "statement": f"{stat.new_value} {stat.subject}", "value": stat.new_value, "unit": stat.unit,
            "subject": stat.subject, "source_ref": "Metrics report 2026", "tier": "public",
            "valid_from": reality.change_date.isoformat(), "supersedes_id": old["id"]})
        reality.fact_ids[stat.subject] = {"old": old["id"], "new": new["id"]}

    await api.ok("POST", "/confidential-terms", json={"term": spec.codename, "note": "unannounced project",
                                                      "embargo_until": reality.embargo_until.isoformat()})
    tokens = {"admin": admin["token"]}
    for role in ("creator", "approver"):
        user = await api.ok("POST", "/users", json={"email": f"{role}@{slug}.example.com", "name": f"Sim {role}",
                                                    "role": role, "clearance": "internal"})
        tokens[role] = user["token"]
    return tokens


# --- turning a template into a case ---------------------------------------------------------------

def instantiate(t: Template, reality: Reality, rng: random.Random, store: Store, case_id: str) -> Case:
    spec = reality.spec
    pieces = SLOT.split(t.body)  # text, slot id, text, slot id, ...
    by_id = {s.id: s for s in t.slots}
    body, plants = "", []
    for i, piece in enumerate(pieces):
        if i % 2 == 0:
            body += piece
            continue
        slot = by_id.get(piece)
        if slot is None:
            continue
        if slot.type == "brand":
            p = casing_plant(store.pick(arms_for("casing"), rng).split(":")[1], spec.name)
        elif slot.type in ("term", "codename"):
            family = "banned" if slot.type == "term" else "codename"
            variant = store.pick(arms_for(family), rng).split(":", 1)[1]
            p = term_plant(family, variant, slot.ref, store.adversarial(family, slot.ref), rng)
        else:
            stat = next(s for s in spec.stats if s.subject == slot.ref)
            variant = store.pick(arms_for("stat"), rng).split(":", 1)[1]
            # LLM text writes its own "%" after the slot; the offline lines don't.
            p = stat_plant(variant, stat.old_value, stat.new_value,
                           percent=stat.unit == "%" and t.source == "offline")
        p.start, p.end = len(body), len(body) + len(p.text)
        body += p.text
        plants.append(p)

    case = Case(case_id, t, body, plants)
    if rng.random() < 0.6:
        family = rng.choice([f for f in APPENDED if f != "hype" or spec.hype_examples])
        arm = store.pick(arms_for(family), rng)
        ctx = {"brand": spec.name, "product": rng.choice(spec.products), "industry": spec.industry,
               "audience": spec.audience}
        p = appended_plant(family, arm.split(":")[1], ctx, spec.hype_examples, rng)
        sep = "\n\n"
        p.start = len(case.body) + len(sep)
        p.end = p.start + len(p.text)
        case.body += sep + p.text
        case.plants.append(p)
    if rng.random() < 0.35:
        p, extra = attachment_plant(store.pick(arms_for(rng.choice(["alt", "contrast"])), rng))
        for k, v in extra.items():
            case.attachments[k] += v
        case.plants.append(p)
    return case


# --- running and grading one case -----------------------------------------------------------------

async def run_case(api: Api, case: Case, reality: Reality, tokens: dict[str, str], cfg: Config) -> dict[str, Any]:
    out: dict[str, Any] = {"case": case, "review": None, "grade": None, "errors": []}
    try:
        submitted = await api.ok("POST", "/contents", token=tokens["creator"], json={
            "title": case.template.title[:300] or "untitled", "channel": case.template.channel, "tier": "public",
            "body": case.body, "attachments": case.attachments})
        review = await api.wait_review(submitted["review_id"], cfg.review_timeout_s)
        out["review"] = review
        out["grade"] = grade(case.body, case.plants, review, codename=reality.spec.codename,
                             banned=list(reality.spec.banned))
        blockers = [f for f in review.get("findings") or [] if f.get("level") == "blocker"]
        if cfg.gate_checks and blockers:
            res = await api.call("POST", f"/contents/{submitted['content']['id']}/transition",
                                 token=tokens["approver"], json={"to": "approved"})
            if res.status_code < 300:
                out["errors"].append(("gate_bypassed", f"approved with {len(blockers)} blocker(s)"))
    except ServerError as exc:
        out["errors"].append(("server_error", str(exc)))
    except Exception as exc:  # noqa: BLE001, a crashed case is a result, not a reason to stop the campaign
        out["errors"].append(("harness_or_api_error", f"{type(exc).__name__}: {exc}"[:500]))
    return out


ADVERSARY_SYSTEM = (
    "You help red-team a brand-compliance filter. Given a phrase the filter must catch, invent new ways a real "
    "person might write that exact phrase in a post so that any human reader still instantly reads it as the "
    "same phrase: spelling tricks, separators, symbols, emoji in the middle, unicode look-alikes, deliberate "
    "typos. Do not paraphrase into different words. Return {\"variants\": [8 strings]}."
)


async def adversary_step(llm: OllamaChat, model: str, store: Store, run_id: int,
                         results: list[dict[str, Any]]) -> int:
    seen: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: {"missed": [], "caught": []})
    for r in results:
        g = r["grade"]
        if g is None or not g.verdicts:
            continue
        for p, v in zip(r["case"].plants, g.verdicts, strict=True):
            if p.family in ("banned", "codename"):
                ref = next((s.ref for s in r["case"].template.slots
                            if s.type == ("term" if p.family == "banned" else "codename")), None)
                if ref:
                    seen[(p.family, ref)]["missed" if v["verdict"] == "missed" else "caught"].append(p.text)
    added = 0
    for (family, term), lists in list(seen.items())[:4]:
        user = (f"Phrase: {term!r}\nSlipped past the filter: {lists['missed'][:6]}\n"
                f"Caught by the filter: {lists['caught'][:6]}\nInvent 8 new spellings.")
        try:
            raw = await llm.json(model, ADVERSARY_SYSTEM, user, temperature=1.0)
        except RuntimeError:
            continue
        variants = [v for v in (raw.get("variants") if isinstance(raw, dict) else []) or []
                    if isinstance(v, str) and 0 < len(v) <= 80 and v != term]
        added += store.add_adversarial(family, term, variants, run_id)
    return added


# --- the campaign ---------------------------------------------------------------------------------

async def campaign(cfg: Config, log=print) -> int:
    store = Store()
    run_id = store.start_run(asdict(cfg))
    rng = random.Random(cfg.seed + run_id)
    llm = None
    if cfg.gen == "llm":
        key = load_key()
        if key is None:
            raise SystemExit("gen=llm needs OLLAMA_API_KEY (env or backend/.env)")
        llm = OllamaChat(key)

    started = time.time()
    totals: Counter[str] = Counter()
    names: list[str] = []
    try:
        for r_idx in range(cfg.realities):
            reality = (await llm_reality(llm, cfg.world_model, rng, date.today(), names) if llm
                       else offline_reality(rng, date.today(), avoid=names))
            names.append(reality.name)
            log(f"reality {r_idx + 1}/{cfg.realities}: {reality.name} ({reality.spec.industry})")
            async with Server(cfg.review) as srv:
                api = Api(srv.url)
                try:
                    tokens = await load_reality(api, reality)
                    templates = (await llm_templates(llm, cfg.gen_model, reality, rng, cfg.templates) if llm
                                 else offline_templates(reality, rng, cfg.templates))
                    log(f"  {len(templates)} templates ({'llm' if llm else 'offline'})")
                    for gen in range(cfg.generations):
                        cases = [instantiate(t, reality, rng, store, f"r{r_idx}g{gen}t{ti}f{fi}")
                                 for ti, t in enumerate(templates) for fi in range(cfg.fills)]
                        sem = asyncio.Semaphore(cfg.concurrency)
                        results = await asyncio.gather(*(_bounded(sem, api, c, reality, tokens, cfg)
                                                         for c in cases))
                        gen_counts = _record(store, run_id, gen, reality, results)
                        totals.update(gen_counts)
                        log(f"  gen {gen + 1}: {len(cases)} cases, caught {gen_counts['caught']}/"
                            f"{gen_counts['caught'] + gen_counts['missed']}, false positives "
                            f"{gen_counts['false_positive']}, invariant breaks {gen_counts['invariant']}")
                        if llm and cfg.adversary and gen + 1 < cfg.generations:
                            added = await adversary_step(llm, cfg.gen_model, store, run_id, results)
                            log(f"  adversary added {added} new spellings")
                    audit = await api.ok("GET", "/audit/verify")
                    if not (audit.get("ok") if isinstance(audit, dict) else False):
                        store.add_failure(run_id, "-", "audit_chain_broken", None, str(audit)[:500])
                        totals["invariant"] += 1
                finally:
                    await api.aclose()
    finally:
        summary = {"seconds": round(time.time() - started, 1), "realities": names, **totals,
                   "llm_calls": llm.calls if llm else 0, "llm_tokens": llm.tokens if llm else 0}
        store.finish_run(run_id, summary)
        if llm:
            await llm.aclose()
        store.close()
    return run_id


async def _bounded(sem: asyncio.Semaphore, api: Api, case: Case, reality: Reality, tokens: dict[str, str],
                   cfg: Config) -> dict[str, Any]:
    async with sem:
        return await run_case(api, case, reality, tokens, cfg)


def _record(store: Store, run_id: int, gen: int, reality: Reality, results: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for r in results:
        case: Case = r["case"]
        g = r["grade"]
        counts["cases"] += 1
        for kind, detail in r["errors"]:
            store.add_failure(run_id, case.case_id, kind, None, detail)
            counts["invariant"] += 1
        if g is not None:
            # An unfinished review has no plant verdicts, only the invariant
            # failure saying so; plants in it count as neither caught nor missed.
            for p, v in zip(case.plants, g.verdicts or [], strict=False):
                failed = v["verdict"] in ("missed", "false_positive")
                store.record(p.arm, failed)
                counts[v["verdict"]] += 1
                if failed:
                    store.add_failure(run_id, case.case_id, v["verdict"], p.arm,
                                      f"{p.text!r} expected {p.expect} in {','.join(p.categories)}")
            for kind, detail in g.invariant_failures:
                store.add_failure(run_id, case.case_id, kind, None, detail)
                counts["invariant"] += 1
            counts["unplanned"] += len(g.unplanned)
        store.save_case(run_id, {
            "case_id": case.case_id, "generation": gen, "reality": reality.name, "genre": case.template.genre,
            "channel": case.template.channel, "source": case.template.source, "body": case.body,
            "plants": [asdict(p) for p in case.plants],
            "findings": [{k: f.get(k) for k in ("title", "category", "level", "span_start", "span_end", "quote",
                                                "checker", "confidence")}
                         for f in ((r["review"] or {}).get("findings") or [])],
            "verdicts": {"plants": g.verdicts if g else [], "unplanned": g.unplanned if g else [],
                         "errors": r["errors"]},
        })
    store.commit()
    return counts
