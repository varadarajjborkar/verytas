"""A brand team's dismissal outlives a re-check.

Each check makes its findings afresh, so a finding the brand team cleared (an escalation answered in the
creator's favour, a reviewer's "not a breach") would come back undecided the moment the creator saves a new
version, and hold the piece up for a call that was already made. When a check finishes, each of the earlier
check's dismissals is copied onto the same issue in the new one: the same rule or fact on the same words, the
occurrence in the same sentence. Changed words, or the same words in a rewritten sentence, are a new
issue and get a fresh call.

Only the brand team's dismissals carry, never the creator's own, and never onto a finding that is more severe
now than when it was dismissed: clearing a must-fix is an approver's call, and a carry must not make it for
them. The copy points at the decision it came from, so learning (calibration, precedents, the clarifier)
counts the call once.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from verytas.models import ContentVersion, Decision, DecisionAction, Finding, Level, Review, ReviewStatus, Role, User

_SEVERITY = {Level.advisory: 0, Level.warning: 1, Level.blocker: 2}
# Where a sentence ends, for telling whether the words around a flagged phrase were rewritten.
_ENDS = ".!?\n\u0964"
# Earlier checks of the piece searched for a call. A piece is rarely re-checked more than a few times.
LOOK_BACK = 20
# Who may clear a must-fix finding (api/content.py decide, api/governance.py resolve_escalation), checked again
# at carry time so a call made by someone who no longer holds that role is not repeated for them.
_CLEARS_BLOCKERS = {Role.approver, Role.brand_admin}


def _key(f: Finding) -> tuple[Any, ...]:
    # Typed text is placed by what surrounds it (_around); a picture's or page's words by their locator.
    where = None if f.source == "body" else json.dumps(f.locator, sort_keys=True, default=str)
    return f.rule_id, f.fact_id, f.quote, f.source, where


def _around(f: Finding, body: str) -> str | None:
    """The sentence that holds the flagged words, whitespace evened out; None when the finding has no place
    in the typed text. A fix made elsewhere in the piece leaves it alone; rewording around the words does not."""
    if f.source != "body" or f.span_start is None or f.span_end is None:
        return None
    start = max((body.rfind(c, 0, f.span_start) for c in _ENDS), default=-1) + 1
    ends = [i for i in (body.find(c, f.span_end) for c in _ENDS) if i >= 0]
    return " ".join(body[start:min(ends) + 1 if ends else len(body)].split())


async def carry_dismissals(session: AsyncSession, review: Review, content_id: int) -> list[dict[str, Any]]:
    """Copy the brand team's dismissals from this piece's earlier checks onto this review's matching findings
    (flushed, not committed). Returns what was carried, for the audit entry.

    A match is the same rule or fact on the same words in the same place: in the typed text, the same words
    in the same sentence (a rewritten sentence is a new call to make); anywhere else (a picture's text, a page
    or slide), the same words at the same locator. The newest call on the issue is the one that counts, so a
    finding upheld after it was once cleared stays upheld, and a check in between that nobody answered (one
    run before this carry existed) does not lose the call made before it."""
    earlier = (await session.scalars(
        select(Review).join(ContentVersion, ContentVersion.id == Review.version_id)
        .where(ContentVersion.content_id == content_id, Review.id < review.id, Review.status == ReviewStatus.done)
        .order_by(Review.id.desc()).limit(LOOK_BACK))).all()
    if not earlier:
        return []
    bodies = {v.id: v.body or "" for v in (await session.scalars(
        select(ContentVersion).where(ContentVersion.id.in_({r.version_id for r in earlier} | {review.version_id}))))}
    order = {r.id: i for i, r in enumerate(earlier)}
    version_of = {r.id: r.version_id for r in earlier}
    # Every decided finding from those checks, newest check first.
    calls: dict[tuple[Any, ...], list[tuple[Finding, Decision, str | None]]] = defaultdict(list)
    decided = (await session.scalars(select(Finding).options(selectinload(Finding.decisions))
                                     .where(Finding.review_id.in_(list(order)), Finding.decisions.any()))).all()
    for f in sorted(decided, key=lambda f: (order[f.review_id], f.id)):
        # Without the words it was about, a call can't be told apart from one on another picture or page.
        if f.quote:
            calls[_key(f)].append((f, f.decisions[-1], _around(f, bodies[version_of[f.review_id]])))
    if not calls:
        return []
    actors = {d.actor_id for options in calls.values() for _, d, _ in options}
    roles = dict((await session.execute(select(User.id, User.role).where(User.id.in_(actors)))).all())
    new_body = bodies.get(review.version_id, "")

    await session.flush()
    carried = []
    used: set[int] = set()
    for new in (await session.scalars(select(Finding).where(Finding.review_id == review.id)
                                      .order_by(Finding.id))).all():
        if not new.quote:
            continue
        here = _around(new, new_body)
        # Paired on the sentence each occurrence sits in, not on its order, so deleting the cleared mention
        # and keeping an uncleared one does not hand the call to the survivor.
        hit = next(((f, d) for f, d, there in calls.get(_key(new), []) if there == here and f.id not in used), None)
        if hit is None:
            continue
        f, last = hit
        used.add(f.id)
        if last.action is not DecisionAction.rejected:
            continue
        role = roles.get(last.actor_id)
        if role is None or role is Role.creator:
            continue
        if _SEVERITY[new.level] > _SEVERITY[f.level]:
            continue
        if new.level is Level.blocker and role not in _CLEARS_BLOCKERS:
            continue
        session.add(Decision(finding_id=new.id, actor_id=last.actor_id, action=DecisionAction.rejected,
                             reason_code=last.reason_code, reason_text=last.reason_text,
                             carried_from_id=last.carried_from_id or last.id))
        carried.append({"finding_id": new.id, "from_finding_id": f.id, "decision_id": last.carried_from_id or last.id})
    return carried
