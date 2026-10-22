"""Governance insights: recurring problems and guideline health.

Guideline health is the ambiguity detector from the design board. For each rule
it combines three signals from human decisions (architecture section 9):

  override rate     how often reviewers reject the rule's findings
  unclear share     how many of those rejections say "guideline unclear"
  disagreement      spread between reviewers' acceptance rates on the same rule

and a Beta(1+accepted, 1+rejected) posterior on "reviewers agree with this
rule". Recommendations are advice for a brand admin; nothing changes a rule
automatically.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from verytas.api.deps import CurrentUser, Session
from verytas.models import (
    Content,
    ContentVersion,
    Decision,
    DecisionAction,
    Finding,
    Review,
    ReviewStatus,
    Rule,
)

router = APIRouter(prefix="/insights", tags=["insights"])
MIN_DECISIONS = 3


def beta_summary(accepted: int, rejected: int) -> dict:
    a, b = accepted + 1, rejected + 1
    mean = a / (a + b)
    sd = math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))
    # Normal approximation to the 5th percentile; good enough to rank rules.
    return {"mean": round(mean, 3), "lower_90": round(max(0.0, mean - 1.645 * sd), 3)}


async def _workspace_findings(session, workspace_id: int) -> list[Finding]:
    q = (select(Finding).options(selectinload(Finding.decisions))
         .join(Review, Finding.review_id == Review.id)
         .join(ContentVersion, Review.version_id == ContentVersion.id)
         .join(Content, ContentVersion.content_id == Content.id)
         .where(Content.workspace_id == workspace_id))
    return list((await session.scalars(q)).all())


@router.get("/overview")
async def overview(session: Session, user: CurrentUser, days: int = 30) -> dict:
    ws = user.workspace_id
    contents = (await session.scalars(select(Content).where(Content.workspace_id == ws))).all()
    reviews = (await session.scalars(
        select(Review).join(ContentVersion, Review.version_id == ContentVersion.id)
        .join(Content, ContentVersion.content_id == Content.id).where(Content.workspace_id == ws))).all()
    findings = await _workspace_findings(session, ws)
    rules = {r.id: r for r in (await session.scalars(select(Rule).where(Rule.workspace_id == ws))).all()}

    decisions = [d for f in findings for d in f.decisions]
    by_action = Counter(d.action.value for d in decisions)
    acted = by_action["accepted"] + by_action["edited"] + by_action["rejected"]

    since = datetime.now(UTC).date() - timedelta(days=days - 1)
    trend: dict[str, Counter] = {(since + timedelta(days=i)).isoformat(): Counter() for i in range(days)}
    for f in findings:
        day = f.created_at.date().isoformat()
        if day in trend:
            trend[day][f.level.value] += 1

    top_rules = Counter(f.rule_id for f in findings if f.rule_id)
    return {
        "content": dict(Counter(c.status.value for c in contents)),
        "reviews": {"total": len(reviews), "done": sum(r.status is ReviewStatus.done for r in reviews),
                    "failed": sum(r.status is ReviewStatus.failed for r in reviews)},
        "findings": {"total": len(findings), "by_level": dict(Counter(f.level.value for f in findings)),
                     "by_category": dict(Counter(f.category for f in findings))},
        "decisions": {**dict(by_action),
                      "acceptance_rate": round((by_action["accepted"] + by_action["edited"]) / acted, 3)
                      if acted else None},
        "top_rules": [{"rule_id": rid, "code": rules[rid].code, "title": rules[rid].title, "findings": n}
                      for rid, n in top_rules.most_common(8) if rid in rules],
        "trend": [{"day": d, **{lvl: c[lvl] for lvl in ("blocker", "warning", "advisory")}}
                  for d, c in trend.items()],
    }


@router.get("/recurring")
async def recurring(session: Session, user: CurrentUser, min_count: int = 2) -> list[dict]:
    """The same rule tripping on the same phrase across content: a training or template problem."""
    findings = await _workspace_findings(session, user.workspace_id)
    rules = {r.id: r for r in (await session.scalars(
        select(Rule).where(Rule.workspace_id == user.workspace_id))).all()}
    groups: dict[tuple[int, str], list[Finding]] = defaultdict(list)
    for f in findings:
        if f.rule_id and f.quote and len(f.quote) <= 80:
            groups[(f.rule_id, f.quote.strip().lower())].append(f)
    out = [{"rule": rules[rid].code, "title": rules[rid].title, "phrase": phrase, "count": len(fs),
            "reviews": len({f.review_id for f in fs})}
           for (rid, phrase), fs in groups.items() if len(fs) >= min_count and rid in rules]
    return sorted(out, key=lambda r: -r["count"])


def _health(rule: Rule, findings: list[Finding]) -> dict:
    decisions: list[Decision] = [d for f in findings for d in f.decisions]
    accepted = sum(d.action in (DecisionAction.accepted, DecisionAction.edited) for d in decisions)
    rejected = sum(d.action is DecisionAction.rejected for d in decisions)
    unclear = sum(d.reason_code == "guideline_unclear" for d in decisions)
    acted = accepted + rejected

    per_actor: dict[int, list[bool]] = defaultdict(list)
    for d in decisions:
        if d.action is not DecisionAction.escalated:
            per_actor[d.actor_id].append(d.action is not DecisionAction.rejected)
    rates = [sum(v) / len(v) for v in per_actor.values() if len(v) >= 2]
    disagreement = (max(rates) - min(rates)) if len(rates) >= 2 else 0.0

    override_rate = rejected / acted if acted else 0.0
    unclear_share = unclear / rejected if rejected else 0.0
    enough = acted >= MIN_DECISIONS
    ambiguity = round(0.4 * override_rate + 0.35 * unclear_share + 0.25 * disagreement, 3) if enough else None
    posterior = beta_summary(accepted, rejected)

    advice = []
    if enough and ambiguity is not None and ambiguity >= 0.5:
        advice.append("clarify wording: reviewers keep overriding or disagreeing on this rule")
    if acted >= 5 and posterior["lower_90"] < 0.3 and rule.severity.value != "may":
        advice.append("consider lowering severity: reviewers rarely agree with its findings")
    if unclear >= 2:
        advice.append("add a good and a bad example: several rejections say the guideline is unclear")
    return {
        "rule_id": rule.id, "code": rule.code, "title": rule.title, "severity": rule.severity.value,
        "findings": len(findings), "decisions": acted, "accepted": accepted, "rejected": rejected,
        "override_rate": round(override_rate, 3), "unclear_share": round(unclear_share, 3),
        "reviewer_disagreement": round(disagreement, 3), "agreement_posterior": posterior,
        "ambiguity": ambiguity, "enough_data": enough, "advice": advice,
    }


@router.get("/guideline-health")
async def guideline_health(session: Session, user: CurrentUser) -> list[dict]:
    findings = await _workspace_findings(session, user.workspace_id)
    rules = (await session.scalars(select(Rule).where(Rule.workspace_id == user.workspace_id))).all()
    by_rule: dict[int, list[Finding]] = defaultdict(list)
    for f in findings:
        if f.rule_id:
            by_rule[f.rule_id].append(f)
    report = [_health(r, by_rule[r.id]) for r in rules if by_rule.get(r.id)]
    return sorted(report, key=lambda h: (h["ambiguity"] is None, -(h["ambiguity"] or 0), -h["findings"]))
