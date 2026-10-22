"""Prism: plans a review, fans it out to workers, and writes signed results.

Workers are stateless and short-lived: each gets only the units plus the rules
and facts it needs, so contexts stay small and nothing has to be retired
mid-review. (The 170k context-cap protocol applies to long-lived agents such as
the Disambiguity agent; see docs/architecture.md 6.2.)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from verytas.checks.base import CheckContext, FactView, RawFinding, RuleView, TermView
from verytas.checks.claims import check_claims
from verytas.checks.deterministic import run_deterministic
from verytas.checks.semantic import check_semantic
from verytas.config import Settings
from verytas.ingest.segment import image_units, segment
from verytas.models import (
    ConfidentialTerm,
    ContentVersion,
    Fact,
    Finding,
    Review,
    ReviewStatus,
    Rule,
    RuleStatus,
    Suggestion,
    utcnow,
)
from verytas.prism.governor import CircuitBreaker, Governor, GuardedJudge, GuardedLLM, TaskOutcome
from verytas.prism.judge import level_for, scorecard
from verytas.prism.suggest import explain_and_fix
from verytas.providers import build_providers
from verytas.providers.base import JudgeProvider, LLMProvider, ProviderError, UsageMeter
from verytas.security.audit import append
from verytas.security.redaction import RedactingJudge, RedactingLLM, Redactor
from verytas.security.signing import AgentKeyring

log = logging.getLogger("verytas.prism")

# Which check families each worker covers, for the "not checked" scorecard.
_COVERS = {
    "deterministic-worker": {"terminology", "accessibility", "confidentiality", "visual", "legal"},
    "claims-worker": {"claims"},
    "semantic-worker": {"tone", "messaging"},
}


def finding_payload(review_id: int, f: Finding | RawFinding, rule_id: int | None) -> dict[str, Any]:
    """The exact fields a worker signs. Re-verifying on read uses the same shape."""
    return {
        "review_id": review_id, "unit_id": f.unit_id, "category": f.category, "title": f.title,
        "explanation": f.explanation, "quote": f.quote, "span": [f.span_start, f.span_end],
        "rule_id": rule_id, "fact_id": f.fact_id, "confidence": round(float(f.confidence), 4),
        "checker": f.checker, "model": f.model,
    }


class Prism:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.keyring = AgentKeyring(settings.keys_dir)
        # Breakers outlive a single review so a dead provider isn't hammered.
        self._llm_breaker = CircuitBreaker()
        self._judge_breaker = CircuitBreaker()
        self._background: set[asyncio.Task[None]] = set()

    def schedule(self, review_id: int) -> None:
        task = asyncio.create_task(self.run(review_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def drain(self) -> None:
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)

    async def run(self, review_id: int) -> None:
        async with self.sessionmaker() as session:
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

    async def _review(self, session: AsyncSession, review_id: int) -> None:
        review = await session.get(Review, review_id)
        version = await session.scalar(
            select(ContentVersion).options(selectinload(ContentVersion.content))
            .where(ContentVersion.id == review.version_id)
        )
        content = version.content
        review.status, review.started_at = ReviewStatus.running, utcnow()
        await session.commit()

        ctx, redactor = await self._context(session, version)
        meter = UsageMeter(self.settings.review_token_budget)
        judge, llm, notes = self._providers(meter, redactor)

        governor = Governor(self.settings.max_concurrent_tasks, self.settings.task_timeout_s)

        async def deterministic() -> list[RawFinding]:
            # CPU-bound (image k-means), so keep it off the event loop.
            return await asyncio.to_thread(run_deterministic, ctx)

        outcomes: dict[str, TaskOutcome] = dict(zip(_COVERS, await asyncio.gather(
            governor.run("deterministic-worker", deterministic),
            governor.run("claims-worker", lambda: check_claims(ctx, llm, judge)),
            governor.run("semantic-worker", lambda: check_semantic(
                ctx, judge, threshold=self.settings.semantic_flag_threshold)),
        ), strict=True))

        rules = {r.code: r for r in ctx.rules}
        worker_of: dict[int, str] = {}
        raw: list[RawFinding] = []
        for worker, outcome in outcomes.items():
            for f in outcome.findings:
                worker_of[id(f)] = worker
                raw.append(f)

        suggest_note = None
        try:
            await asyncio.wait_for(explain_and_fix(raw, rules, llm, judge), timeout=self.settings.task_timeout_s)
        except (ProviderError, TimeoutError) as exc:
            suggest_note = f"explanations and fixes skipped: {exc or 'timed out'}"

        checked: set[str] = set()
        for worker, outcome in outcomes.items():
            if outcome.status == "ok":
                checked |= _COVERS[worker]

        levelled = []
        dropped = 0
        for f in raw:
            rule = rules.get(f.rule_code or "")
            if rule is None and f.fact_id is None:
                dropped += 1  # uncitable; the schema would reject it anyway
                continue
            lvl = level_for(f, rule, blocker_confidence=self.settings.blocker_confidence)
            levelled.append((f, lvl))
            payload = finding_payload(review.id, f, rule.id if rule else None)
            signature = self.keyring.sign(worker_of[id(f)], payload)
            if not self.keyring.verify(signature, payload):  # pragma: no cover - defensive
                raise RuntimeError("signature failed self-verification")
            row = Finding(
                review_id=review.id, unit_id=f.unit_id, category=f.category, level=lvl, title=f.title,
                explanation=f.explanation, quote=f.quote, span_start=f.span_start, span_end=f.span_end,
                rule_id=rule.id if rule else None, fact_id=f.fact_id, confidence=round(float(f.confidence), 4),
                checker=f.checker, model=f.model, signature=signature,
            )
            session.add(row)
            if f.suggestion:
                await session.flush()
                s = f.suggestion
                session.add(Suggestion(finding_id=row.id, original=s.original, proposed=s.proposed,
                                       rationale=s.rationale, intent_preserved=s.intent_preserved, model=s.model))

        card = scorecard(levelled, checked)
        review.summary = card.as_dict()
        review.coverage = {
            "workers": {w: {"status": o.status, "note": o.note, "findings": len(o.findings), "ms": o.duration_ms}
                        for w, o in outcomes.items()},
            "not_checked": sorted({c for w, o in outcomes.items() if o.status != "ok" for c in _COVERS[w]}),
            "notes": notes + ([suggest_note] if suggest_note else []) + (
                [f"{dropped} uncited finding(s) dropped"] if dropped else []),
            # AI disclosure: every external model that saw (redacted) content.
            "models": {"llm": llm.name, "judge": judge.name},
            "usage": meter.by_provider,
            "redactions": redactor.count,
        }
        review.status, review.finished_at = ReviewStatus.done, utcnow()
        await append(session, workspace_id=content.workspace_id, actor="agent:prism", action="review.completed",
                     object_type="review", object_id=review.id,
                     detail={"version_id": version.id, "blockers": card.blockers, "warnings": card.warnings,
                             "advisories": card.advisories, "models": review.coverage["models"],
                             "not_checked": review.coverage["not_checked"]})
        await session.commit()

    async def _context(self, session: AsyncSession, version: ContentVersion) -> tuple[CheckContext, Redactor]:
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
            attachments=attachments, channel=content.channel,
        )
        # Every confidential term is redacted on egress, embargoed or not.
        return ctx, Redactor([t.term for t in terms])

    def _providers(self, meter: UsageMeter, redactor: Redactor) -> tuple[JudgeProvider, LLMProvider, list[str]]:
        judge, llm, notes = build_providers(self.settings, meter)
        if not judge.name.startswith("offline"):
            judge = RedactingJudge(judge, redactor)
        if not llm.name.startswith("offline"):
            llm = RedactingLLM(llm, redactor)
        return GuardedJudge(judge, self._judge_breaker), GuardedLLM(llm, self._llm_breaker), notes

