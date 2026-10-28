"""Prism: plans a review, fans it out to workers, and writes signed results.

Prism spawns a tree of agents shaped by the submission (prism/agents.py): a
text agent per piece of text, an image agent per image (with OCR, asset and
scene agents under it), a document agent per file (with a page agent per page),
then the onion layers (prism/onion.py) over everything found. Workers are
stateless and short-lived, so contexts stay small and nothing has to be retired
mid-review. (The 170k context-cap protocol applies to long-lived agents such as
the Disambiguity agent; see docs/architecture.md 6.2.)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import UTC, date, datetime
from typing import Any

import cv2
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from verytas.checks.base import CheckContext, ContactView, FactView, RawFinding, RuleView, TermView
from verytas.checks.claims import drop_fixes_that_keep_claims
from verytas.checks.likeness import PersonView
from verytas.checks.voice import BrandProfile, build_profile
from verytas.config import Settings
from verytas.ingest.language import NAMES, WORD_LISTS, Language, detect
from verytas.ingest.segment import image_units, segment
from verytas.media import assets as asset_match
from verytas.media.files import decode_b64, open_image, png_b64, shrink
from verytas.media.storage import blob_ids
from verytas.models import (
    BrandAsset,
    BrandEvent,
    ConfidentialTerm,
    Content,
    ContentStatus,
    ContentVersion,
    Dispute,
    Fact,
    Finding,
    Level,
    MediaBlob,
    Person,
    PublicContact,
    Review,
    ReviewStatus,
    Rule,
    RuleStatus,
    Suggestion,
    Tier,
    Workspace,
    utcnow,
)
from verytas.prism import calibration, fixstyle, precedent, research
from verytas.prism.agents import MEDIA_COVERS, WORKER_COVERS, AgentTree, OfficialAsset, ReviewRun, plan
from verytas.prism.dedupe import collapse
from verytas.prism.disputes import is_mechanical, rule_thresholds
from verytas.prism.governor import CircuitBreaker, Governor, GuardedJudge, GuardedLLM
from verytas.prism.intent import intent_agent
from verytas.prism.judge import CATEGORIES, WARN_CONFIDENCE, level_for, scorecard
from verytas.prism.onion import onion_agent
from verytas.prism.people_agent import PeopleContext
from verytas.prism.second_look import SecondLook
from verytas.prism.suggest import explain_and_fix
from verytas.providers import build_providers, build_second_judge, build_vision, build_web_search
from verytas.providers.base import JudgeProvider, LLMProvider, ProviderError, UsageMeter
from verytas.security.audit import append
from verytas.security.guard import screen
from verytas.security.redaction import RedactingJudge, RedactingLLM, Redactor
from verytas.security.signing import AgentKeyring

log = logging.getLogger("verytas.prism")

# Signing identity per worker. The first three keep their original key names,
# so findings signed before the agent tree still verify.
_SIGNER = {"rule checks": "deterministic-worker", "claim verifier": "claims-worker",
           "semantic judge": "semantic-worker", "assets": "assets-worker", "media": "media-worker",
           "context": "context-worker", "intake": "intake-worker", "intent": "intent-worker",
           "presentation": "presentation-worker", "cross-check": "crosscheck-worker"}
# What each kind of agent is responsible for. Any node that was skipped, timed
# out or crashed demotes exactly these categories, so a gap anywhere in the
# tree shows up in the scorecard instead of reading as a pass.
_MEDIA_ROLES = {"image", "ocr", "document", "page", "ocr-fallback", "video", "captions", "speech", "subtitles"}
_ALL_TEXT = set().union(*WORKER_COVERS.values())
_ROLE_COVERS: dict[str, set[str]] = {
    **{r: MEDIA_COVERS for r in _MEDIA_ROLES},
    "prism": set(CATEGORIES), "text": _ALL_TEXT,
    "policy": {"messaging", "legal"}, "presentation": {"legal", "visual", "accessibility"},
    "contrast": {"accessibility"},
    "faces": {"legal"},
    "characters": {"visual"},
    "crosscheck": {"claims"},
}
_ASSET_ROLES = {"assets", "scene", "keyframes"}  # visual, when the workspace has official artwork
# Context reading is a second opinion over text that was already checked:
# losing it degrades messaging rather than leaving it unchecked.
_DEGRADING_ROLES = {"context", "context-layer", "verifier", "emoji"}


def _coverage_gaps(gaps, has_assets: bool) -> tuple[set[str], set[str]]:
    """(not checked, degraded) categories implied by the agents that did not finish."""
    failed: set[str] = set()
    degraded: set[str] = set()
    for n in gaps:
        if n.role == "worker":
            failed |= WORKER_COVERS.get(n.label, set())
        elif n.role in _ASSET_ROLES:
            if has_assets:
                failed.add("visual")
        elif n.role in _DEGRADING_ROLES:
            degraded.add("messaging")
        else:
            failed |= _ROLE_COVERS.get(n.role, set())
    return failed, degraded


def finding_payload(review_id: int, f: Finding | RawFinding, rule_id: int | None, level: str,
                    fix: tuple[str, str] | None) -> dict[str, Any]:
    """The exact fields a worker signs. Re-verifying on read uses the same shape.

    Level and the suggested fix are included because they are what the approval
    gate and apply-fixes act on; editing either in the database breaks the seal.
    """
    payload = {
        "review_id": review_id, "unit_id": f.unit_id, "category": f.category, "title": f.title,
        "explanation": f.explanation, "quote": f.quote, "span": [f.span_start, f.span_end],
        "rule_id": rule_id, "fact_id": f.fact_id, "confidence": round(float(f.confidence), 4),
        "checker": f.checker, "model": f.model, "level": level, "fix": list(fix) if fix else None,
    }
    # Provenance is sealed too, so a finding can't be moved to another image or
    # page. Body findings keep the original shape (and existing signatures).
    source = getattr(f, "source", None) or "body"
    if source != "body":
        payload["source"] = source
        payload["locator"] = getattr(f, "locator", None)
    return payload


class Prism:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.keyring = AgentKeyring(settings.keys_dir)
        # Breakers outlive a single review so a dead provider isn't hammered.
        self._llm_breaker = CircuitBreaker()
        self._judge_breaker = CircuitBreaker()
        self._vision_breaker = CircuitBreaker()
        self._second_breaker = CircuitBreaker()
        # Claim research: one search client and one daily allowance shared by every review.
        self._web = build_web_search(settings)
        self._research_cap = research.DailyCap(settings.research_per_day, settings.research_per_workspace_day)
        # One pool of provider slots shared by every review, so a long document
        # (one Jev call per paragraph) or a burst of reviews can't flood a provider.
        self._provider_slots = asyncio.Semaphore(settings.max_concurrent_tasks)
        self._admission = asyncio.Semaphore(settings.max_concurrent_reviews)
        self._background: set[asyncio.Task[None]] = set()

    async def _research(self, raw: list[RawFinding], judge, redactor: Redactor, brand: str | None,
                        workspace_id: int) -> dict:
        """Web results for unsupported claims (prism/research.py). Bounded in time; whatever goes wrong is
        recorded and never fails the review. The log is shared with the search so that a timeout still lists
        the searches that were made, matching the results already on the findings."""
        log: dict = {"provider": self._web.name, "searched": [], "skipped": 0}
        try:
            await asyncio.wait_for(
                research.research(raw, self._web, judge, redactor.mask, brand, self._research_cap,
                                  self.settings.research_per_review, workspace=workspace_id, log=log),
                timeout=self.settings.task_timeout_s)
        except TimeoutError:
            log["note"] = "timed out"
        except Exception as exc:  # noqa: BLE001, research is evidence only; nothing it does may fail a review
            log["note"] = f"failed: {type(exc).__name__}"
        return log

    def schedule(self, review_id: int) -> None:
        task = asyncio.create_task(self.run(review_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def recover(self) -> int:
        """After a restart nothing is running: a review cut off part-way, or still waiting for a slot, is run
        again from the start. Its findings are written only in the transaction that finishes it, so an
        interrupted one has none to duplicate."""
        async with self.sessionmaker() as session:
            stuck = (await session.scalars(select(Review.id).where(
                Review.status.in_((ReviewStatus.queued, ReviewStatus.running))))).all()
            if stuck:
                await session.execute(update(Review).where(Review.id.in_(stuck)).values(
                    status=ReviewStatus.queued, started_at=None))
                await session.commit()
        for review_id in stuck:
            self.schedule(review_id)
        if stuck:
            log.info("re-running %d review(s) interrupted by a restart", len(stuck))
        return len(stuck)

    async def drain(self) -> None:
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)

    async def run(self, review_id: int) -> None:
        async with self._admission, self.sessionmaker() as session:
            try:
                await self._review(session, review_id)
            except Exception as exc:  # noqa: BLE001, record the failure on the review itself
                log.exception("review %s failed", review_id)
                await session.rollback()
                review = await session.get(Review, review_id)
                if review is not None:
                    review.status = ReviewStatus.failed
                    review.error = f"{type(exc).__name__}: review crashed"
                    review.finished_at = utcnow()
                    await session.commit()

    def _waker(self):
        """One waker per process, so concurrent reviews share a single start of the worker instance."""
        if not self.settings.vision_worker_instance_id or not self.settings.vision_worker_url:
            return None
        if getattr(self, "_vision_waker", None) is None:
            from verytas.vision.wake import Waker

            self._vision_waker = Waker(self.settings.vision_worker_instance_id,
                                       f"{self.settings.vision_worker_url.rstrip('/')}/health",
                                       self.settings.vision_wake_timeout_s)
        return self._vision_waker

    async def _review(self, session: AsyncSession, review_id: int) -> None:
        review = await session.get(Review, review_id)
        version = await session.scalar(
            select(ContentVersion).options(selectinload(ContentVersion.content))
            .where(ContentVersion.id == review.version_id)
        )
        content = version.content
        review.status, review.started_at = ReviewStatus.running, utcnow()
        await session.commit()
        # Wall time per phase, kept on the review: where a slow review spent its time, without a profiler.
        phases: dict[str, int] = {}
        clock = [time.perf_counter()]

        def lap(name: str) -> None:
            now = time.perf_counter()
            phases[name] = round((now - clock[0]) * 1000)
            clock[0] = now

        ctx, redactor, assets = await self._context(session, version)
        book = await precedent.load(session, content.workspace_id, content.tier, redactor.mask)
        workspace = await session.get(Workspace, content.workspace_id)
        brand = workspace.name if workspace else None
        # Which kind of fix reviewers take per rule, and their own edits (prism/fixstyle.py). Seeded by the
        # version, so a re-run of the same version prefers the same operations.
        style = await fixstyle.load(session, content.workspace_id, content.tier, redactor.mask, seed=version.id)
        language = detect(version.body)
        blobs = await _load_blobs(session, content.workspace_id, version.attachments or {}, version.creator_notes or {})
        visuals_any = _has_visuals(version.attachments or {})
        visuals = self.settings.faces_enabled and visuals_any
        people = await _people(session, content, ctx, self.settings) if visuals else None
        cleared = await _cleared_disputes(session, content.id)
        # Learned from disputes and reviewer decisions: how sure the judge must
        # be before each model-judged rule flags (prism/disputes.py).
        thresholds = await rule_thresholds(session, content.workspace_id, self.settings.semantic_flag_threshold)
        # What a certainty has meant to this workspace's reviewers (prism/calibration.py).
        calib = await calibration.load(session, content.workspace_id, content.tier)
        # Close the read transaction before any model call. A live review spends
        # tens of seconds waiting on providers; holding a transaction that long
        # starves every other writer on SQLite and pins an old snapshot on
        # Postgres. The writes at the end run in a fresh, short transaction.
        await session.commit()
        meter = UsageMeter(self.settings.review_token_budget)
        judge, llm, vision, notes = self._providers(meter, redactor)

        governor = Governor(self.settings.max_concurrent_tasks, self.settings.task_timeout_s)
        tree = AgentTree(self.settings.agent_max_depth, self.settings.agent_max_nodes)
        run = ReviewRun(
            base=ctx, llm=llm, judge=judge, vision=vision, governor=governor, tree=tree,
            rule_by_code={r.code: r for r in ctx.rules}, assets=assets, content_tier_rank=content.tier.rank,
            # Confidential content never leaves the machine as pixels: text can be
            # redacted, an image can only be partly blacked out.
            allow_cloud_vision=not vision.name.startswith("offline") and content.tier is not Tier.confidential,
            semantic_threshold=self.settings.semantic_flag_threshold,
            ocr_min_confidence=self.settings.ocr_min_confidence,
            blobs=blobs, profile=(version.attachments or {}).get("profile") or {},
            declared_ai=bool((version.creator_notes or {}).get("ai_used")),
            asr_model=self.settings.asr_model, asr_long_model=self.settings.asr_long_model,
            asr_long_seconds=_small_model_seconds(self.settings.asr_long_seconds, self.settings.media_timeout_s),
            asr_vocabulary=_vocabulary(ctx, assets),
            brand_names=_brand_names(ctx, assets),
            video_max_seconds=self.settings.video_max_seconds,
            media_timeout_s=self.settings.media_timeout_s,
            rule_thresholds=thresholds,
            second_look=self._second_look(redactor),
            precedents=book, precedent_examples=self.settings.precedent_examples,
        )

        escalations: list[dict] = []
        notes_realm = dict(version.creator_notes or {})
        if audio := blobs.get(notes_realm.get("brief_audio_blob_id") or ""):
            # The voice-note brief, as text: screened like any note below, read by the intent agent, and
            # the names in it are what the visual checks look for.
            said = await _transcribe_brief(run, audio)
            if said:
                notes_realm["brief"] = " ".join(filter(None, [notes_realm.get("brief"), f"(voice note) {said}"]))
        run.brief = notes_realm.get("brief") or ""
        run.people = people
        if self.settings.vision_worker_url and visuals_any:
            from verytas.vision.client import VisionClient

            token = self.settings.vision_worker_token
            try:
                run.characters = VisionClient(self.settings.vision_worker_url,
                                              token.get_secret_value() if token else None,
                                              self.settings.vision_worker_timeout_s, wake=self._waker())
            except ValueError as exc:
                run.notes.append(f"vision worker not used: {exc}")
        # Offers and off-the-record contact in the note go to a person whatever the model makes of it.
        # (Steering is the intent agent's call: it reads the note against each finding.)
        note_text = " ".join(v for v in notes_realm.values() if isinstance(v, str))
        # Contact details are flagged rather than refused now, so both lists are read.
        guarded = screen(note_text, ctx.contacts) if note_text.strip() else None
        for flag in [*guarded.refused, *guarded.flagged] if guarded else []:
            if flag.code in ("inducement", "contact_exchange"):
                escalations.append({"reason": f"creator note: {flag.label}", "detail": flag.quote})

        rules = {r.code: r for r in ctx.rules}
        terms = [t.term for t in ctx.terms]
        # Explanations and fixes for the literal findings are written while the context layers read the
        # post: those findings are final once plan() returns (later steps only drop duplicates or cap a
        # level), so they need not wait for the slowest model work. The context findings follow after.
        early: list[asyncio.Task] = []

        async def prism(root):
            await plan(run, root)
            first = [f for f in run.findings if f.needs_explanation]
            if first:
                early.append(asyncio.create_task(asyncio.wait_for(
                    explain_and_fix(first, rules, llm, judge, terms, style=style),
                    timeout=self.settings.task_timeout_s)))
            await tree.spawn(root, "context", "Onion: context layers", lambda n: onion_agent(run, n), essential=True)
            # One finding per issue before anything spends a model call on each.
            run.findings[:] = collapse(run.findings)
            # Last, and apart from every check: what the creator says it means.
            found = await tree.spawn(root, "intent", "Weigh the creator's note",
                                     lambda n: intent_agent(run, n, notes_realm, run.sources), essential=True)
            escalations.extend(found or [])

        lap("setup")
        try:
            await tree.spawn(None, "prism", "Prism", prism)
        except BaseException:
            for t in early:
                t.cancel()
            raise
        lap("checks")
        raw = run.findings
        with_precedent = book.attach(raw, {s.id: s.text for s in run.sources})
        # Searched while the fixes are written: it needs only the claims, and adds no wait of its own.
        researching = (asyncio.create_task(self._research(raw, judge, redactor, brand, content.workspace_id))
                       if self._web is not None and content.tier is Tier.public else None)
        try:
            _apply_cleared(raw, cleared, {r.code: r.id for r in ctx.rules})
            rule_problems = run.rule_problems
            worker_of = run.worker_of

            suggest_note = None
            try:
                for t in early:
                    await t
                # Whatever is still unexplained: the context layers' findings, mostly.
                await asyncio.wait_for(explain_and_fix(raw, rules, llm, judge, terms, style=style),
                                       timeout=self.settings.task_timeout_s)
            except (ProviderError, TimeoutError) as exc:
                suggest_note = f"explanations and fixes skipped: {exc or 'timed out'}"
            else:
                lap("explain_and_fix")
                try:
                    await asyncio.wait_for(drop_fixes_that_keep_claims(raw, ctx, llm, judge),
                                           timeout=self.settings.task_timeout_s)
                except (ProviderError, TimeoutError) as exc:
                    # A claim fix nobody could re-check may just restate the claim: withhold it.
                    for f in raw:
                        if f.category == "claims" and f.suggestion and f.suggestion.model:
                            f.suggestion = None
                    suggest_note = f"AI-written claim fixes withheld (could not re-check them): {exc or 'timed out'}"

            research_log = await researching if researching is not None else None
        finally:
            # An early exit (an error, a cancelled review) must not leave the search running and spending the cap.
            if researching is not None and not researching.done():
                researching.cancel()

        # Coverage must never be claimed when it didn't happen. A category is
        # "checked" only if a rule for it exists, every worker that covers it
        # ran on every piece of text, and no media part it depends on was left
        # unread. Semantic categories judged by the offline heuristic, and
        # context layers that could not run, are degraded rather than passed.
        configured = {r.category for r in ctx.rules}
        failed: set[str] = set()
        for outcome in run.outcomes:
            if outcome.status != "ok":
                failed |= WORKER_COVERS.get(outcome.name, set())
        failed |= {category for _, category, _ in rule_problems}
        gap_failed, gap_degraded = _coverage_gaps(tree.gaps(), bool(assets))
        failed |= gap_failed
        checked = configured - failed
        degraded = {"tone", "messaging"} & checked if judge.name.startswith("offline") else set()
        degraded |= (gap_degraded | run.partial) & checked
        statuses = {c: ("not_configured" if c not in configured else "not_checked" if c in failed
                        else "degraded" if c in degraded else "checked") for c in CATEGORIES}
        notes = notes + run.notes + _gap_notes(tree.gaps()) + _language_notes(language)

        levelled = []
        held_back: set[int] = set()
        dropped = 0
        for f in raw:
            rule = rules.get(f.rule_code or "")
            if rule is None and f.fact_id is None:
                dropped += 1  # uncitable; the schema would reject it anyway
                continue
            lvl = level_for(f, rule, blocker_confidence=self.settings.blocker_confidence,
                            warn_confidence=calib.warn_confidence(f, WARN_CONFIDENCE, rule))
            if (lvl is Level.advisory and f.level_cap != "advisory"
                    and level_for(f, rule, blocker_confidence=self.settings.blocker_confidence) is Level.warning):
                held_back.add(id(f))  # the learned floor, not the rule or a cap, made this an advisory
            if f.level_cap == "advisory":
                lvl = Level.advisory
            levelled.append((f, lvl))
            fix = (f.suggestion.original, f.suggestion.proposed) if f.suggestion else None
            payload = finding_payload(review.id, f, rule.id if rule else None, lvl.value, fix)
            signature = self.keyring.sign(_SIGNER[worker_of[id(f)]], payload)
            if not self.keyring.verify(signature, payload):  # pragma: no cover - defensive
                raise RuntimeError("signature failed self-verification")
            row = Finding(
                review_id=review.id, unit_id=f.unit_id, category=f.category, level=lvl, title=f.title,
                explanation=f.explanation, quote=f.quote, span_start=f.span_start, span_end=f.span_end,
                rule_id=rule.id if rule else None, fact_id=f.fact_id, confidence=round(float(f.confidence), 4),
                checker=f.checker, model=f.model, signature=signature, source=f.source, locator=f.locator,
                assessment=f.assessment, precedents=f.precedents, research=f.research,
                calibration=_calibrated(calib, f, id(f) in held_back),
            )
            session.add(row)
            if f.suggestion:
                await session.flush()
                s = f.suggestion
                session.add(Suggestion(finding_id=row.id, original=s.original, proposed=s.proposed,
                                       rationale=s.rationale, intent_preserved=s.intent_preserved, model=s.model,
                                       action=s.action))

        lap("recheck_and_store")
        card = scorecard(levelled, checked, statuses)
        review.summary = card.as_dict()
        review.coverage = {
            "workers": _worker_summary(run.outcomes),
            # How Prism checked this submission: every agent it spawned.
            "agents": tree.as_list(),
            # Every piece of text found and how it was obtained (typed, text layer, OCR).
            "sources": [{"id": s.id, "kind": s.kind, "route": s.route, "confidence": round(s.confidence, 3),
                         "locator": s.locator, "parent": s.parent, "chars": len(s.text),
                         "text": s.text[:20_000]} for s in run.sources],
            "scenes": run.scenes,
            # What the agents posted for each other to compare (prism/board.py), by kind.
            "evidence": run.board.summary(),
            "language": {"code": language.code, "name": language.name, "mixed": list(language.mixed)},
            # Things a person has to look at: notes that steer, concerns, unsure disputes.
            "escalations": escalations,
            "learned_thresholds": thresholds,
            "calibration": calib.summary(),
            "fix_style": style.summary(),
            "research": research_log,
            # Must-rule questions answered by the larger judge too, with both answers.
            "second_looks": run.second_look.summary() if run.second_look else None,
            "precedents": {**book.summary(), "attached": with_precedent, "examples": self.settings.precedent_examples},
            "not_checked": sorted(failed & configured),
            "not_configured": sorted(set(CATEGORIES) - configured),
            "degraded": sorted(degraded),
            "rule_errors": [f"{code}: {err}" for code, _, err in rule_problems],
            "notes": notes + ([suggest_note] if suggest_note else []) + (
                [f"{dropped} uncited finding(s) dropped"] if dropped else []),
            # AI disclosure: every external model that saw (redacted) content.
            "models": {"llm": llm.name, "judge": judge.name, "vision": vision.name,
                       **({"second_judge": run.second_look.judge.name} if run.second_look else {})},
            "usage": meter.by_provider,
            "redactions": redactor.count,
            "phases_ms": phases,
        }
        # Agent details come from numpy-heavy media code; store plain JSON only.
        review.coverage = _plain(review.coverage)
        review.status, review.finished_at = ReviewStatus.done, utcnow()
        if escalations:
            await append(session, workspace_id=content.workspace_id, actor="agent:prism", action="review.escalated",
                         object_type="review", object_id=review.id,
                         detail={"reasons": [e["reason"] for e in escalations]})
        await append(session, workspace_id=content.workspace_id, actor="agent:prism", action="review.completed",
                     object_type="review", object_id=review.id,
                     detail={"version_id": version.id, "blockers": card.blockers, "warnings": card.warnings,
                             "advisories": card.advisories, "models": review.coverage["models"],
                             "not_checked": review.coverage["not_checked"]})
        await session.commit()

    async def _context(self, session: AsyncSession,
                       version: ContentVersion) -> tuple[CheckContext, Redactor, list[OfficialAsset]]:
        content = version.content
        ws = content.workspace_id
        rules = (await session.scalars(
            select(Rule).where(Rule.workspace_id == ws, Rule.status == RuleStatus.active)
        )).all()
        facts = (await session.scalars(select(Fact).where(Fact.workspace_id == ws, Fact.approved))).all()
        terms = (await session.scalars(select(ConfidentialTerm).where(ConfidentialTerm.workspace_id == ws))).all()

        # Tier ceiling: a public post is only checked against facts it could
        # legitimately cite. Confidential facts never feed lower-tier content.
        visible_facts = [f for f in facts if f.tier.rank <= content.tier.rank]
        # Same ceiling for rules: a confidential rule's text and source must not
        # appear in findings on lower-tier content (or reach a model through it).
        rules = [r for r in rules if r.tier.rank <= content.tier.rank]
        # Event rules apply while their event runs (a crisis brief covers every post), or to a piece made
        # for that event even before it starts; hashtag rules only to pieces tagged with the event.
        today = date.today()
        events = {e.id: e for e in (await session.scalars(
            select(BrandEvent).where(BrandEvent.workspace_id == ws))).all()}

        def applies(r: Rule) -> bool:
            if r.event_id is None:
                return True
            event = events.get(r.event_id)
            if event is None or event.status != "active":
                return False
            tagged = content.event_id == r.event_id
            if (r.pattern or {}).get("type") == "event_hashtags":
                return tagged
            return tagged or event.live_on(today)

        rules = [r for r in rules if applies(r)]
        contacts = (await session.scalars(
            select(PublicContact).where(PublicContact.workspace_id == ws, PublicContact.active))).all()
        attachments = version.attachments or {}
        ctx = CheckContext(
            body=version.body,
            units=segment(version.body) + image_units(attachments),
            rules=[RuleView(r.id, r.code, r.category, r.kind.value, r.severity.value, r.title, r.text,
                            tuple(r.good_examples or ()), tuple(r.bad_examples or ()), dict(r.pattern or {}))
                   for r in rules],
            facts=[FactView(f.id, f.statement, f.value, f.unit, f.subject, f.source_ref, f.valid_from, f.valid_to)
                   for f in visible_facts],
            terms=[TermView(t.id, t.term, t.embargo_until) for t in terms],
            contacts=[ContactView(c.kind, c.value, c.normalized, c.label) for c in contacts],
            attachments=attachments, channel=content.channel,
            profile=await _brand_profile(session, content, rules, visible_facts, list(events.values())),
        )
        rows = (await session.scalars(
            select(BrandAsset).where(BrandAsset.workspace_id == ws, BrandAsset.active))).all()
        assets = await asyncio.to_thread(_prepare_assets, rows, content.tier.rank)
        # Every confidential term is redacted on egress, embargoed or not.
        return ctx, Redactor([t.term for t in terms]), assets

    def guarded_providers(self, redactor: Redactor) -> tuple[JudgeProvider, LLMProvider, LLMProvider, list[str]]:
        """Providers for work outside a review (disputes, AI edits): same guards and redaction."""
        return self._providers(UsageMeter(self.settings.review_token_budget), redactor)

    def schedule_job(self, coro_factory) -> None:
        task = asyncio.create_task(coro_factory())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def _second_look(self, redactor: Redactor) -> SecondLook | None:
        # Its own token budget, a quarter of a review's: a second look that runs long can't starve the first
        # judge, whose answers are the ones that count when the second is unavailable.
        meter = UsageMeter(self.settings.review_token_budget // 4)
        judge = build_second_judge(self.settings, meter)
        if judge is None:
            return None
        guarded = GuardedJudge(RedactingJudge(judge, redactor), self._second_breaker, self._provider_slots)
        return SecondLook(guarded, self.settings.second_look_max, meter=meter)

    def _providers(self, meter: UsageMeter,
                   redactor: Redactor) -> tuple[JudgeProvider, LLMProvider, LLMProvider, list[str]]:
        judge, llm, notes = build_providers(self.settings, meter)
        vision, vision_notes = build_vision(self.settings, meter)
        if not judge.name.startswith("offline"):
            judge = RedactingJudge(judge, redactor)
        if not llm.name.startswith("offline"):
            llm = RedactingLLM(llm, redactor)
        if not vision.name.startswith("offline"):
            # Text parts of vision requests (captions, reference names) are
            # redacted like any prompt; pixels were blacked out before this.
            vision = RedactingLLM(vision, redactor)
        return (GuardedJudge(judge, self._judge_breaker, self._provider_slots),
                GuardedLLM(llm, self._llm_breaker, self._provider_slots),
                GuardedLLM(vision, self._vision_breaker, self._provider_slots), notes + vision_notes)


# Profiles by (database, workspace, tier, the approved versions they came from, the topic texts): an unchanged
# brand costs one id query per review, and any approval, edit or new fact makes a new key.
_PROFILES: OrderedDict[tuple, BrandProfile] = OrderedDict()
_PROFILE_SOURCES = 150


async def _brand_profile(session: AsyncSession, content: Content, rules: list[Rule], facts: list[Fact],
                         events: list[BrandEvent]) -> BrandProfile:
    """The brand's own voice and topics (checks/voice.py), learned from what it has approved or published.
    Same tier ceiling as facts: a public post is never measured against confidential work."""
    tiers = [t for t in Tier if t.rank <= content.tier.rank]
    latest = func.max(ContentVersion.id)
    ids = tuple((await session.scalars(
        select(latest).join(Content, ContentVersion.content_id == Content.id)
        .where(Content.workspace_id == content.workspace_id, Content.tier.in_(tiers), Content.id != content.id,
               Content.status.in_((ContentStatus.approved, ContentStatus.published)))
        .group_by(ContentVersion.content_id).order_by(latest.desc()).limit(_PROFILE_SOURCES))).all())
    # Rule examples widen the topics but don't count as approved work: the explanation says "N pieces".
    topics = [ex for r in rules if r.category in ("tone", "messaging") for ex in (r.good_examples or [])]
    topics += [f.statement for f in facts] + [f"{e.name}. {e.summary} {e.guidance}" for e in events
                                              if e.status == "active" and e.tier.rank <= content.tier.rank]
    # Version bodies never change once written, so their ids stand for their text within one database; the engine
    # is part of the key because ids repeat across databases (tests, a reseeded demo) in one process.
    key = (id(session.get_bind()), content.workspace_id, content.tier.rank, ids, hash(tuple(topics)))
    if (hit := _PROFILES.get(key)) is not None:
        _PROFILES.move_to_end(key)
        return hit
    bodies = list((await session.scalars(select(ContentVersion.body).where(ContentVersion.id.in_(ids)))).all()
                  ) if ids else []
    profile = await asyncio.to_thread(build_profile, bodies, topics)
    _PROFILES[key] = profile
    while len(_PROFILES) > 32:
        _PROFILES.popitem(last=False)
    return profile


def _language_notes(language: Language) -> list[str]:
    """Say plainly which checks could read the piece, mixes included. Checks that can't stay quiet, not guess."""
    if language.code == "und" or (language.code == "en" and not language.mixed):
        return []
    notes = [f"Written in {language.name}. Names, terms, numbers, contacts and links are checked in any language, "
             "and the model judge reads all of it."]
    unread = [NAMES.get(c, c) for c in (language.code, *language.mixed) if c not in WORD_LISTS]
    if unread:
        notes.append(f"The tone and topic word lists don't cover {' or '.join(unread)}, so drift in those parts rests "
                     "on the model judge.")
    notes.append("The reading-grade check is English only, so it does not grade text in other languages.")
    return notes


def _worker_summary(outcomes) -> dict[str, dict]:
    """Per text worker across every source: did it run everywhere, how long, how much found."""
    out: dict[str, dict] = {}
    for o in outcomes:
        w = out.setdefault(o.name, {"status": "ok", "note": None, "findings": 0, "ms": 0, "runs": 0})
        w["runs"] += 1
        w["findings"] += len(o.findings)
        w["ms"] = max(w["ms"], o.duration_ms)
        if o.status != "ok":
            w["status"], w["note"] = o.status, o.note
    return out


# Fingerprinting artwork is the slow part of matching, and assets change
# rarely: keep the prepared form across reviews, keyed by content hash.
_PREPARED: OrderedDict[tuple[int, str], tuple[Image.Image, asset_match.PreparedAsset, str]] = OrderedDict()
_PREPARED_MAX = 64
_PREPARED_LOCK = threading.Lock()


def _prepare_assets(rows, content_rank: int) -> list[OfficialAsset]:
    """Decode and fingerprint the workspace's official artwork, from cache where possible."""
    prepared = []
    for row in rows:
        key = (row.id, hashlib.sha256(row.data_base64.encode()).hexdigest())
        with _PREPARED_LOCK:
            hit = _PREPARED.get(key)
            if hit:
                _PREPARED.move_to_end(key)
        if hit is None:
            try:
                img = open_image(decode_b64(row.data_base64, 8 * 1024 * 1024))
                hit = (img, asset_match.prepare(row.id, img), png_b64(shrink(img, 768)))
            except (ValueError, cv2.error):  # MediaError is a ValueError
                log.warning("brand asset %s could not be prepared; skipped", row.id)
                continue
            with _PREPARED_LOCK:
                _PREPARED[key] = hit
                while len(_PREPARED) > _PREPARED_MAX:
                    _PREPARED.popitem(last=False)
        img, fingerprint, b64 = hit
        prepared.append(OfficialAsset(
            id=row.id, name=row.name, kind=row.kind, part=row.part, restricted=row.tier.rank > content_rank,
            image=img, prepared=fingerprint, b64=b64, wordmark=row.wordmark, retired=bool(row.retired),
        ))
    return prepared


async def _load_blobs(session: AsyncSession, workspace_id: int, attachments: dict,
                      notes: dict | None = None) -> dict[str, bytes]:
    ids = blob_ids(attachments, notes)
    if not ids:
        return {}
    rows = (await session.scalars(
        select(MediaBlob).where(MediaBlob.id.in_(ids), MediaBlob.workspace_id == workspace_id))).all()
    return {b.id: b.data for b in rows}



def _has_visuals(attachments: dict) -> bool:
    return bool(attachments.get("images") or attachments.get("videos") or attachments.get("documents"))


async def _people(session: AsyncSession, content: Content, ctx: CheckContext, settings: Settings) -> PeopleContext:
    """The brand's approved people and their photos, and whether names may be looked up on the web."""
    rows = (await session.scalars(select(Person).options(selectinload(Person.references))
                                  .where(Person.workspace_id == content.workspace_id, Person.active))).all()
    people = [PersonView(id=p.id, name=p.name, kind=p.kind, valid_from=p.valid_from, valid_to=p.valid_to,
                         channels=tuple(p.channels or ()), event_ids=tuple(p.event_ids or ()), user_id=p.user_id,
                         active=p.active, aliases=tuple(p.aliases or ())) for p in rows]
    photos = {p.id: [base64.b64decode(r.data_base64) for r in p.references if r.approved] for p in rows}
    return PeopleContext(
        people=people, photos=photos, restricted={p.id for p in rows if p.tier.rank > content.tier.rank},
        channel=content.channel, event_id=content.event_id, author_id=content.created_by,
        on=datetime.now(UTC).date(), models_dir=settings.vision_models_dir,
        # A name in a confidential brief can itself be the secret (an unannounced deal): it never leaves.
        allow_web=settings.llm_mode != "offline" and content.tier is not Tier.confidential,
        avoid=[t.term for t in ctx.terms])


# Whisper small ran at 0.66 times real time on 8 cores (evals/speech) and slows about in step with fewer.
SMALL_RTF_8_CORES = 0.66


def _small_model_seconds(configured: int, timeout_s: float, cores: int | None = None) -> int:
    """The longest audio the better speech model gets on this machine: the configured length, cut so the
    expected transcription takes at most half the media timeout. On the 2 vCPU server that is about half
    a minute; a minute and a half of speech on small would run past the timeout and leave it unchecked."""
    cores = cores or os.cpu_count() or 1
    rtf = SMALL_RTF_8_CORES * 8 / min(cores, 8)
    return min(configured, int(timeout_s / 2 / rtf))


VOCABULARY_CHARS = 400  # Whisper reads at most 224 prompt tokens; names past this would be cut anyway


def _vocabulary(ctx, assets: list[OfficialAsset]) -> str:
    """The brand's public names as a Whisper prompt."""
    out = ""
    for name in _brand_names(ctx, assets):  # whole names only: a cut one is a new word to listen for
        if len(out) + len(name) + 2 > VOCABULARY_CHARS:
            break
        out = f"{out}, {name}" if out else name
    return out


def _brand_names(ctx, assets: list[OfficialAsset]) -> list[str]:
    """The brand's public names, for speech recognition and OCR repair: product and brand spellings from
    its rules, and the lettering of its current artwork. Confidential terms and restricted artwork stay
    out."""
    names: list[str] = []
    for r in ctx.rules:
        kind = (r.pattern or {}).get("type")
        if kind == "casing":
            names += list(r.pattern.get("terms") or [])
        elif kind == "preferred_terms":
            names += list((r.pattern.get("map") or {}).values())
    for a in assets:
        if a.official and not a.restricted:
            names += [a.wordmark] if a.wordmark else []
    seen, out = set(), []
    for n in names:
        n = str(n).strip()
        # Either way round: "Falcon" primes Whisper toward a confidential "Project Falcon" too.
        low = n.lower()
        if n and low not in seen and not any(t.term.lower() in low or low in t.term.lower() for t in ctx.terms):
            seen.add(n.lower())
            out.append(n)
    return out


async def _transcribe_brief(run: ReviewRun, audio: bytes) -> str:
    """What the creator said in a voice-note brief, or "" with a note when it can't be read."""
    from verytas.media import video

    async def listen() -> str:
        pcm = await run.blocking(video.audio_pcm, audio, max_seconds=600)
        if pcm is None:
            return ""
        cues, _, _ = await run.blocking(video.transcribe, pcm, run.asr_for(pcm), run.asr_vocabulary)
        return " ".join(c.text for c in cues).strip()

    try:
        said = await asyncio.wait_for(listen(), run.media_timeout_s)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001, a bad voice note costs the brief, never the review
        run.notes.append(f"the voice-note brief could not be transcribed ({type(exc).__name__})")
        return ""
    if not said:
        run.notes.append("the voice-note brief has no speech we could transcribe")
    return said


def _gap_notes(gaps) -> list[str]:
    """One note per gap, except budget skips, which are summarised: a long document can skip dozens."""
    skipped = [n.label for n in gaps if n.status == "skipped"]
    notes = [f"{n.label}: {n.note}" for n in gaps if n.note and n.status != "skipped"]
    if skipped:
        shown = ", ".join(skipped[:5]) + (f" and {len(skipped) - 5} more" if len(skipped) > 5 else "")
        notes.append(f"{len(skipped)} agent(s) skipped because the review's agent budget was reached: {shown}")
    return notes


async def _cleared_disputes(session: AsyncSession, content_id: int) -> list[tuple[int | None, str | None, str, int]]:
    """(rule_id, quote, source, dispute_id) for disputes on this content that were overturned."""
    rows = (await session.execute(
        select(Dispute.rule_id, Finding.quote, Finding.source, Dispute.id)
        .join(Finding, Finding.id == Dispute.finding_id)
        .where(Dispute.content_id == content_id, Dispute.status == "overturned"))).all()
    return [(rid, q, src or "body", did) for rid, q, src, did in rows]


def _calibrated(calib: calibration.Calibration, f: RawFinding, held_back: bool) -> dict | None:
    """How often reviewers agreed with findings like this, and whether the learned floor held it back."""
    out = calib.of(f) or {}
    if held_back:
        out["held_back_below"] = calib.floor
    return out or None


def _apply_cleared(findings: list[RawFinding], cleared: list[tuple[int | None, str | None, str, int]],
                   rule_ids: dict[str, int]) -> None:
    """A reading already overturned on re-evaluation isn't raised at full weight again.
    It still shows, capped at advisory and linked to the dispute, so a reviewer can see it.

    Keyed by rule, quote and where it was found. A finding without a quote
    (an image-level asset verdict) matches only on the same image or page,
    never every quote-less finding of that rule."""
    index = {(rid, (q or "").strip().lower(), src): did for rid, q, src, did in cleared}
    for f in findings:
        did = index.get((rule_ids.get(f.rule_code or ""), (f.quote or "").strip().lower(), f.source or "body"))
        if did is not None and not is_mechanical(f):
            f.level_cap = "advisory"
            f.assessment = {**(f.assessment or {}), "by": "dispute", "dispute_id": did,
                            "outcome": "cleared earlier on re-evaluation"}


def _plain(value):
    """Recursively convert numpy scalars and tuples into JSON-native values."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "item") and callable(value.item) and not isinstance(value, (str, bytes)):
        return value.item()  # numpy bool_, float64, int64 ...
    return value
