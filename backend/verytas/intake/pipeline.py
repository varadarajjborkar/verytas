"""Prism Intake: one agent per item, reading, understanding and checking what a company hands over.

For each item, in parallel under one budget:
  read        code turns the file into text, tables and pictures (intake/readers.py; video and audio
              through the review's own speech and frame steps)
  see         the vision model describes each picture; a chart gets its values or "unreadable"
  understand  the model says what the item is and proposes rules, facts, codenames, assets and table
              plans (intake/understand.py); offline, or for confidential material, a plainer reading
  check       code expands table plans into facts cell by cell, validates every draft against the same
              schema the library uses, and flags what a person should look at: a figure that disagrees
              with an approved fact or with another draft, a date already past, a fact with no unit
  ask         an item the model could not place waits as "needs context", with its questions, and
              produces nothing until someone answers

Nothing is saved to the library here. Every candidate becomes a pending draft with where it came from,
and only an admin's approval creates it, through the same endpoint and checks as adding it by hand.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.intake import fetch as live
from verytas.intake import readers, tables
from verytas.intake.understand import DescribeTask, Picture, Understanding, UnderstandTask
from verytas.models import (
    ConfidentialTerm,
    Fact,
    IntakeBatch,
    IntakeDraft,
    IntakeItem,
    MediaBlob,
    Rule,
    RuleStatus,
    Tier,
    User,
    utcnow,
)
from verytas.prism import rulebook
from verytas.schemas import FactIn, TermIn

log = logging.getLogger("verytas.intake")

MAX_PARALLEL = 3
MAX_PICTURES = 6
ITEM_TIMEOUT_S = 240
# Reading runs in threads, and a timed-out item cannot stop its thread, so reads share a small pool of
# their own: however many batches are running, at most this many files are being parsed at once.
_READERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="intake-read")


@dataclass
class Known:
    """What the workspace already has, so a draft is never a copy of it."""
    facts: list[Fact] = field(default_factory=list)  # only those the batch's filer may read
    codes: set[str] = field(default_factory=set)  # rule codes in the library and in pending drafts
    rule_texts: set[str] = field(default_factory=set)
    terms: set[str] = field(default_factory=set)


def public_source(url: str) -> str:
    """A link as it may be shown: no password, query or fragment, where signed links keep their keys."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _pending(item: IntakeItem, target: str, payload: dict[str, Any], provenance: dict[str, Any],
             confidence: float, issues: list[dict[str, Any]] | None = None) -> IntakeDraft:
    return IntakeDraft(item_id=item.id, workspace_id=item.workspace_id, target=target, payload=payload,
                       provenance=provenance, confidence=round(confidence, 3), issues=issues or [])


async def run_batch(prism: Any, batch_id: int) -> None:
    """The background job for one batch. Each item is independent: one that fails says so, the rest go on."""
    async with prism.sessionmaker() as session:
        batch = await session.get(IntakeBatch, batch_id)
        if batch is None:
            return
        batch.status = "running"
        await session.commit()
        ids = list((await session.scalars(select(IntakeItem.id).where(IntakeItem.batch_id == batch_id))).all())
    slots = asyncio.Semaphore(MAX_PARALLEL)

    async def one(item_id: int) -> None:
        async with slots:
            await run_item(prism, item_id)

    await asyncio.gather(*(one(i) for i in ids), return_exceptions=True)
    await summarise(prism, batch_id)


async def rerun_item(prism: Any, item_id: int, batch_id: int) -> None:
    """One item read again (an answer, a refresh), and its batch's counts brought up to date."""
    await run_item(prism, item_id)
    await summarise(prism, batch_id)


async def summarise(prism: Any, batch_id: int) -> None:
    async with prism.sessionmaker() as session:
        batch = await session.get(IntakeBatch, batch_id)
        items = (await session.scalars(select(IntakeItem).where(IntakeItem.batch_id == batch_id))).all()
        ids = [i.id for i in items]
        drafts = (await session.scalars(select(IntakeDraft).where(IntakeDraft.item_id.in_(ids)))).all()
        batch.status = "done" if any(i.status != "failed" for i in items) or not items else "failed"
        batch.finished_at = utcnow()
        batch.summary = {"items": {s: sum(1 for i in items if i.status == s) for s in {i.status for i in items}},
                         "drafts": {t: sum(1 for d in drafts if d.target == t) for t in {d.target for d in drafts}},
                         "flagged": sum(1 for d in drafts if d.issues)}
        await session.commit()


async def run_item(prism: Any, item_id: int) -> None:
    try:
        await asyncio.wait_for(_run_item(prism, item_id), timeout=ITEM_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001, one item failing is recorded on it and never stops the batch
        log.warning("intake item %s failed: %s", item_id, exc)
        async with prism.sessionmaker() as session:
            item = await session.get(IntakeItem, item_id)
            if item is not None:
                item.status = "failed"
                # Our own refusals say what to do; anything else is an internal error, logged, not shown.
                item.error = ("took too long to read" if isinstance(exc, TimeoutError)
                              else str(exc)[:500] if isinstance(exc, (ValueError, live.FetchRefused))
                              else "couldn't be read; try again or export it in another format")
                await session.commit()


async def recover(sessionmaker: Any) -> None:
    """After a restart nothing is still reading: what was mid-way is marked so a person can run it again."""
    async with sessionmaker() as session:
        await session.execute(update(IntakeItem).where(IntakeItem.status.in_(("queued", "reading"))).values(
            status="failed", error="interrupted by a server restart; refresh or answer it to read it again"))
        await session.execute(update(IntakeBatch).where(IntakeBatch.status.in_(("queued", "running"))).values(
            status="done", finished_at=utcnow()))
        # An approval cut off between creating the library object and recording it: back to pending, flagged,
        # because the object may already exist.
        for d in (await session.scalars(select(IntakeDraft).where(IntakeDraft.status == "applying"))).all():
            d.status = "pending"
            d.issues = [*d.issues, {"kind": "interrupted",
                                    "detail": "an approval was interrupted; check the library before approving"}]
        await session.commit()


async def _load(session: AsyncSession, item: IntakeItem) -> tuple[bytes, str]:
    if item.text is not None:
        return item.text.encode(), readers.sniff_text(item.text.encode()) or "text/plain"
    if item.source_url:
        raw, declared = await live.fetch(item.source_url)
        kind = readers.office_kind(raw) or readers.sniff_text(raw) or declared or "application/octet-stream"
        return raw, kind
    blob = await session.get(MediaBlob, item.blob_id) if item.blob_id else None
    if blob is None or blob.workspace_id != item.workspace_id:
        raise ValueError("the uploaded file is gone; upload it again")
    return bytes(blob.data), blob.media_type


async def _media(prism: Any, raw: bytes, kind: str, reading: readers.Reading) -> None:
    """Video and audio: speech by the local recogniser, and a few frames to look at, as a review reads them."""
    from verytas.media import video

    settings = prism.settings
    pcm = await asyncio.to_thread(video.audio_pcm, raw, max_seconds=settings.video_max_seconds)
    if pcm is not None:
        cues, _, _ = await asyncio.to_thread(video.transcribe, pcm, settings.asr_model)
        reading.text = " ".join(c.text for c in cues)[:readers.MAX_TEXT]
        reading.pages = [c.text for c in cues]
    else:
        reading.notes.append("no speech track")
    if kind.startswith("video/"):
        samples = await asyncio.to_thread(video.frames, raw, max_seconds=settings.video_max_seconds)
        for _, img in video.keyframes(samples, limit=4):
            png = readers._as_png(_png_bytes(img))
            if png:
                reading.images.append(png)


def _png_bytes(img) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def _run_item(prism: Any, item_id: int) -> None:
    async with prism.sessionmaker() as session:
        item = await session.get(IntakeItem, item_id)
        batch = await session.get(IntakeBatch, item.batch_id)
        item.status, item.error = "reading", None
        await session.commit()
        raw, kind = await _load(session, item)
        tier, note = batch.tier, " ".join(x for x in (batch.note, item.context) if x)
        redactor = await _redactor(session, item.workspace_id)
        filer = await session.get(User, batch.created_by)
        known = await _known(session, item, filer)
        await session.commit()  # no transaction across the reading and the model calls

    reading = await asyncio.get_running_loop().run_in_executor(_READERS, readers.read, raw, kind, item.name)
    if kind.startswith(("video/", "audio/")):
        await _media(prism, raw, kind, reading)
    # Confidential material never goes to a hosted model: it gets the offline reading, and pictures wait
    # for a person to say what they are.
    hosted = tier is not Tier.confidential and prism.settings.llm_mode != "offline"
    _, llm, vision, _ = prism.guarded_providers(redactor)
    pictures: list[Picture] = []
    if hosted and reading.images:
        pictures = list(await asyncio.gather(*(_describe(vision, png, note) for png in reading.images[:MAX_PICTURES])))
    task = UnderstandTask(item.name, note, reading, pictures)
    model = "offline-heuristic"
    if hosted:
        try:
            found = await llm.run(task)
            model = llm.name
        except Exception:  # noqa: BLE001, a model failure falls back to the plain reading, named as such
            found = task.heuristic()
    else:
        found = task.heuristic()
    found = _ask_about_pictures(found, reading, pictures, note)

    async with prism.sessionmaker() as session:
        item = await session.get(IntakeItem, item_id)
        await session.execute(delete(IntakeDraft).where(IntakeDraft.item_id == item.id,
                                                        IntakeDraft.status == "pending"))
        drafts, issues = build_drafts(item, found, reading, known, tier, pictures)
        held = {i for i, p in enumerate(pictures) if _unclear(p, note)}
        if reading.kind == "image" and not note.strip() and not pictures:
            held = {0}
        # What came from a picture nobody explained is held back entirely: a guess is worse than a gap.
        # When the item is that picture, that is everything it would add.
        if reading.kind == "image" and 0 in held:
            drafts = []
        drafts = [d for d in drafts if not (d.target == "asset" and d.payload.get("image") in held)
                  and d.provenance.get("picture") not in held]
        if found.questions:
            # Open questions about the item: its drafts stay, each marked, so none goes in by bulk approval.
            for d in drafts:
                d.issues = [*d.issues, {"kind": "open_question", "detail": "answer this item's questions first"}]
        for d in drafts:
            session.add(d)
        item.media_type = kind
        item.kind, item.purpose, item.confidence = found.kind, found.purpose[:500], found.confidence
        item.questions = found.questions
        item.status = "needs_context" if found.questions else "understood"
        item.reading = reading.preview() | {"pictures": [p.model_dump(exclude_defaults=True) for p in pictures]}
        item.issues, item.model = issues, model
        if item.source_url:
            item.refreshed_at = utcnow()
        await session.commit()


async def _known(session: AsyncSession, item: IntakeItem, filer: User | None) -> Known:
    ws = item.workspace_id
    # Facts above the filer's clearance are neither shown in a conflict note nor offered for replacing.
    ceiling = filer.clearance.rank if filer is not None else Tier.public.rank
    # Withdrawn facts are not "in the library", and only a rule's version in force says what it reads now;
    # every code ever used stays taken, since a code can't be created twice.
    facts = [f for f in (await session.scalars(select(Fact).where(Fact.workspace_id == ws, Fact.approved))).all()
             if f.tier.rank <= ceiling]
    newest = select(Rule.code, func.max(Rule.version).label("v")).where(Rule.workspace_id == ws) \
        .group_by(Rule.code).subquery()
    current = (await session.execute(select(Rule.text).join(newest, and_(Rule.code == newest.c.code,
                                                                         Rule.version == newest.c.v))
                                     .where(Rule.workspace_id == ws, Rule.status != RuleStatus.retired))).all()
    codes = set((await session.scalars(select(Rule.code).where(Rule.workspace_id == ws))).all())
    others = (await session.scalars(select(IntakeDraft).where(
        IntakeDraft.workspace_id == ws, IntakeDraft.status.in_(("pending", "applying")),
        IntakeDraft.item_id != item.id, IntakeDraft.target.in_(("rule", "term"))))).all()
    known = Known(facts=facts, codes=codes, rule_texts={_norm(t) for (t,) in current},
                  terms={_norm(t) for t in (await session.scalars(select(ConfidentialTerm.term).where(
                      ConfidentialTerm.workspace_id == ws))).all()})
    for d in others:
        if d.target == "rule":
            known.codes.add(str(d.payload.get("code", "")))
            known.rule_texts.add(_norm(d.payload.get("text")))
        else:
            known.terms.add(_norm(d.payload.get("term")))
    return known


async def _describe(vision: Any, png: bytes, note: str) -> Picture:
    try:
        return await vision.run(DescribeTask(base64.b64encode(png).decode(), note[:500]))
    except Exception:  # noqa: BLE001, an undescribed picture is asked about instead
        return Picture(what="other", description="", readable=False)


async def _redactor(session: AsyncSession, workspace_id: int):
    from verytas.prism.disputes import workspace_redactor

    return await workspace_redactor(session, workspace_id)


def _ask_about_pictures(found: Understanding, reading: readers.Reading, pictures: list[Picture],
                        note: str) -> Understanding:
    """The model may not ask, so code does: a chart that can't be read, or with no title or period, and
    nothing said about it, is a question, not a fact."""
    asks = list(found.questions)
    for i, p in enumerate(pictures):
        if _unclear(p, note):
            asks.append(f"Picture {i + 1} is a chart with no clear title or period. What does it show, "
                        "for which period, and is it approved to quote?")
    if reading.kind == "image" and not pictures and not note.strip() and not found.questions:
        asks.append("What is this picture, and how should it be used: official artwork, a chart, or an example?")
    return found.model_copy(update={"questions": list(dict.fromkeys(asks))[:3]})


def _unclear(p: Picture, note: str) -> bool:
    """A chart nothing explains: no readable values, or no title or period, and no word from the admin."""
    return p.what == "chart" and not note.strip() and (not p.readable or not (p.chart_title and p.chart_period))


def _skeleton(statement: str) -> str:
    return _norm(re.sub(r"\d[\d,.]*", " # ", statement))


def _norm(s: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def build_drafts(item: IntakeItem, found: Understanding, reading: readers.Reading, known: Known, tier: Tier,
                 pictures: list[Picture] | None = None) -> tuple[list[IntakeDraft], list[dict[str, Any]]]:
    """Every candidate as a pending draft, validated, with its source and anything a person should check."""
    drafts: list[IntakeDraft] = []
    issues: list[dict[str, Any]] = []
    # A link is shown without its query: read-only links are often signed, and a rule's source is public.
    source = item.name if not item.source_url else f"{item.name} ({public_source(item.source_url)})"
    # Rules from a brand book govern what goes out, so they reach public posts, as the brand-book importer's
    # do; only material filed as confidential keeps its rules (and their wording) confidential.
    rule_tier = Tier.confidential if tier is Tier.confidential else Tier.public

    # Rules: through the brand-book importer's own coder and validator, one at a time so each keeps its own
    # source sentence, and never a second copy of a rule the library or another draft already has.
    codes, texts, repeats = set(known.codes), set(known.rule_texts), 0
    for cand in found.rules:
        key = _norm(cand.text)
        if not key or key in texts:
            repeats += bool(key)
            continue
        proposal = rulebook.Proposal(category=cand.category, kind=cand.kind, severity=cand.severity,
                                     title=cand.title, text=cand.text, quote=cand.quote, pattern=cand.pattern,
                                     good_examples=cand.good_examples, bad_examples=cand.bad_examples)
        made, skipped = rulebook.to_rules([proposal], codes, source)
        issues += [{"kind": "skipped", "detail": s} for s in skipped]
        if not made:
            continue
        codes.add(made[0].code)
        texts.add(key)
        payload = made[0].model_dump(mode="json") | {"tier": rule_tier.value}
        prov = {"source": source, "where": cand.where, "quote": cand.quote[:300]}
        drafts.append(_pending(item, "rule", payload, prov, found.confidence))
    if repeats:
        issues.append({"kind": "known", "detail": f"{repeats} rule{'s' if repeats > 1 else ''} already in the "
                       "library or another draft, left out"})

    # Facts the model read from prose.
    facts: list[tuple[dict[str, Any], dict[str, Any], float]] = []
    for f in found.facts:
        payload = {"statement": f.statement, "value": f.value, "unit": f.unit, "subject": f.subject,
                   "valid_from": tables.as_date(f.valid_from or "") if f.valid_from else None,
                   "valid_to": tables.as_date(f.valid_to or "") if f.valid_to else None}
        facts.append((payload, {"source": source, "where": f.where, "quote": f.quote[:300]}, found.confidence))
    # Facts from tables: the plan applied by code, cell by cell.
    by_name = {t.name: t for t in reading.tables}
    for plan in found.tables:
        t = by_name.get(plan.table) or (reading.tables[0] if len(reading.tables) == 1 else None)
        if t is None or plan.fact is None:
            continue
        cleaned, origin, notes = tables.apply(t, plan.ops)
        rows, problems = tables.facts(cleaned, plan.fact, origin, source)
        issues += [{"kind": "table", "detail": n} for n in notes + problems[:20]]
        facts += [(r["payload"], r["provenance"], max(found.confidence, 0.6)) for r in rows]

    # A chart handed over on its own: its values come from the picture by code, not again from the model.
    charted = any(p.what == "chart" and p.readable and p.chart_title and p.chart_period for p in pictures or [])
    if reading.kind == "image" and charted:
        facts = [f for f in facts if f[1].get("cell")]
    # Facts read off a chart the vision model could read, with its title and period: lower confidence than
    # a cell, since they were read by eye, and held back entirely when the chart was not explained.
    for i, p in enumerate(pictures or []):
        if p.what != "chart" or not p.readable or not (p.chart_title and p.chart_period):
            continue
        for series in p.series[:4]:
            for label, value in series.points[:24]:
                name = series.name if series.name and series.name.lower() not in p.chart_title.lower() else ""
                statement = f"{p.chart_title}{' (' + name + ')' if name else ''}, {label}: {value:g}" \
                            f"{' ' + p.chart_unit if p.chart_unit else ''} ({p.chart_period})"
                facts.append(({"statement": statement[:500], "value": value, "unit": p.chart_unit,
                               "subject": f"{p.chart_title} {label}"[:200]},
                              {"source": source, "where": f"picture {i + 1}", "picture": i,
                               "quote": f"{label}: {value:g}"}, 0.5))

    seen: dict[tuple[str, str], list[float]] = {}
    already = 0
    for payload, prov, conf in facts:
        flags = []
        payload = {k: v for k, v in payload.items() if v not in (None, "")}
        payload.setdefault("valid_from", date.today())
        payload["source_ref"] = (prov.get("cell") or prov.get("where") or source)[:300]
        payload["tier"] = tier.value
        try:
            checked = FactIn.model_validate(payload)
        except ValidationError as exc:
            why = exc.errors()[0]["msg"]
            issues.append({"kind": "invalid", "detail": f"{payload.get('statement', '')[:80]}: {why}"})
            continue
        if checked.value is not None and not checked.unit:
            flags.append({"kind": "no_unit", "detail": "a figure with no unit; say what it counts"})
        if checked.valid_to and checked.valid_to < date.today():
            flags.append({"kind": "expired", "detail": f"valid only until {checked.valid_to}"})
        # The same claim with another number: the statement with its figures blanked out ("The Pro plan costs
        # Rs #"), so a series (Jan: 42, Feb: 48) is not mistaken for two answers to one question.
        key = (_skeleton(checked.statement), _norm(checked.unit))
        current = [o for o in known.facts if o.valid_to is None and _norm(o.unit) == key[1]
                   and _skeleton(o.statement) == key[0]]
        if checked.value is not None and any(o.value == checked.value for o in current):
            # Already in the library as it stands: a refresh shows what changed, not everything again.
            already += 1
            continue
        if checked.value is not None:
            for other in current:
                if other.value is not None:
                    flags.append({"kind": "conflict", "detail": f"the library says {other.value:g} "
                                  f"({other.statement[:80]}); approving this one replaces it",
                                  "supersedes": other.id})
            values = seen.setdefault(key, [])
            if values and checked.value not in values:
                flags.append({"kind": "conflict", "detail": f"another row in this material gives {values[0]:g} "
                              "for the same thing"})
            values.append(checked.value)
        drafts.append(_pending(item, "fact", checked.model_dump(mode="json"), prov, conf, flags))
    if already:
        issues.append({"kind": "known", "detail": f"{already} figure{'s' if already > 1 else ''} already in the "
                       "library with the same value, left out"})

    for term in found.terms:
        # A codename is a name: a few words with letters in them, on one line.
        if "\n" in term.term or not re.search(r"[^\W\d_]", term.term) or len(term.term.split()) > 5:
            issues.append({"kind": "skipped", "detail": f"not a name: {term.term[:40]!r}"})
            continue
        try:
            checked = TermIn.model_validate({"term": term.term, "note": term.why[:2000]})
        except ValidationError:
            continue
        if _norm(checked.term) in known.terms:
            continue
        known.terms.add(_norm(checked.term))
        drafts.append(_pending(item, "term", checked.model_dump(mode="json"),
                               {"source": source, "quote": term.quote[:300]}, found.confidence))

    for a in found.assets:
        # A video's frames are looked at but not kept, so a frame can't become artwork: export a still.
        if reading.kind in ("video", "audio"):
            continue
        if 0 <= a.image < len(reading.images):
            drafts.append(_pending(item, "asset", {"name": a.name[:120], "kind": a.kind, "image": a.image,
                                                   "tier": tier.value},
                                   {"source": source, "where": f"picture {a.image + 1}"}, found.confidence))
    return drafts, issues
