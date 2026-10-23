"""Calibration: what a finding's certainty has meant, in this workspace, to the people who decide.

A judge that says "75% sure" is not right three times in four; verbalised confidence runs high (Xiong et
al., ICLR 2024), and a rule-based hit at 100% can still be one reviewers dismiss as beside the point. So
each finding also carries how often reviewers agreed with findings like it: an isotonic regression
(pool adjacent violators) from raw certainty to "the reviewer upheld it", fitted on this workspace's
decided findings. Isotonic, because the only thing assumed is that higher certainty should not mean less
agreement; no curve shape is imposed on a few hundred points.

A family is a check category (tone, claims, legal...). One with at least FAMILY_MIN decisions gets its
own curve; otherwise the workspace-wide curve is used once there are WORKSPACE_MIN decisions in all;
below that nothing is claimed and the UI shows the raw certainty, as before.

Warnings from model-judged "should" rules get a learned floor (risk control in the style of
Learn-then-Test, Angelopoulos et al., 2021): once WARN_MIN decisions on such findings exist, the grid is
tested from its strictest certainty down (fixed-sequence testing, so the 90% holds over the whole scan),
each step asking whether reviewers dismiss under WARN_RISK of the findings at or above it (a Hoeffding
bound); the floor is the lowest step reached before a test fails. Bounded like every learned change here:
the floor only moves between 0.6 and 0.85, it only turns a warning into an advisory (still shown, and
marked as held back), and must rules and rule-based findings are never touched. Every number comes from
content at or below the reviewed content's tier.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.checks.base import RawFinding, RuleView
from verytas.models import Content, ContentVersion, Decision, DecisionAction, Finding, Review, Rule, Tier

FAMILY_MIN = 20
WORKSPACE_MIN = 30
WARN_MIN = 50
WARN_RISK = 0.35  # most a reviewer should be asked to dismiss among warnings, as a share
WARN_DELTA = 0.1
WARN_GRID = (0.6, 0.65, 0.7, 0.75, 0.8, 0.85)
PRIOR = 10.0  # pseudo-decisions at the overall rate in every step: a step needs about ten of its own to move far
MAX_DECISIONS = 5000


def agreed(action: DecisionAction | str, reason: str | None) -> bool | None:
    """Did the reviewer agree the finding was right? Kept on purpose ("intentional") still says it was;
    "the guideline is unclear" and escalations say nothing either way."""
    action = DecisionAction(action)
    if action in (DecisionAction.accepted, DecisionAction.edited):
        return True
    if action is DecisionAction.rejected:
        return True if reason == "intentional" else None if reason == "guideline_unclear" else False
    return None


@dataclass(frozen=True)
class Curve:
    """A non-decreasing step function from raw certainty to agreement, with how many decisions it rests on."""
    xs: tuple[float, ...]  # left edge of each step
    ys: tuple[float, ...]
    n: int
    rate: float

    def __call__(self, x: float) -> float:
        i = bisect.bisect_right(self.xs, x) - 1
        return self.ys[max(i, 0)]


def fit(points: list[tuple[float, bool]]) -> Curve:
    """Isotonic regression by pool adjacent violators, each step shrunk towards the overall rate."""
    pts = sorted(points)
    n = len(pts)
    rate = sum(y for _, y in pts) / n
    blocks: list[list[float]] = []  # [left x, sum of y, weight]
    for x, y in pts:
        if blocks and blocks[-1][0] == x:
            blocks[-1][1] += y
            blocks[-1][2] += 1
        else:
            blocks.append([x, float(y), 1.0])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            x2, s, w = blocks.pop()
            blocks[-1][1] += s
            blocks[-1][2] += w
    # Shrunk towards the rate with one agreement and one dismissal added, so a workspace whose few
    # decisions all went one way still isn't read as "always" or "never".
    centre = (rate * n + 1) / (n + 2)
    ys, top = [], 0.0
    for _, s, w in blocks:
        # Shrinking a light step can lift it over a heavier one after it; the running max keeps it monotone.
        top = max(top, (s + PRIOR * centre) / (w + PRIOR))
        ys.append(top)
    return Curve(tuple(b[0] for b in blocks), tuple(ys), n, rate)


def warn_floor(points: list[tuple[float, bool]]) -> float | None:
    """The lowest grid certainty, reached from the top, whose warnings reviewers dismiss under WARN_RISK
    with confidence 1 - delta. A step with too few decisions above it is passed over, not failed."""
    if len(points) < WARN_MIN:
        return None
    floor = WARN_GRID[-1]
    for t in reversed(WARN_GRID):
        above = [y for x, y in points if x >= t]
        if len(above) < 10:
            continue
        dismissed = 1 - sum(above) / len(above)
        if dismissed + math.sqrt(math.log(1 / WARN_DELTA) / (2 * len(above))) > WARN_RISK:
            break
        floor = t
    return floor


@dataclass
class Calibration:
    families: dict[str, Curve] = field(default_factory=dict)
    workspace: Curve | None = None
    floor: float | None = None  # learned warning floor for model-judged should rules
    sizes: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_points(cls, points: list[tuple[str, bool, float, bool]], warned: list[tuple[float, bool]] | None = None,
                    ) -> Calibration:
        """`points` are (category, model-judged?, raw certainty, reviewer agreed?); `warned` the (certainty,
        agreed?) of model-judged findings on should rules, the only ones the warning floor applies to."""
        by_family: dict[str, list[tuple[float, bool]]] = {}
        for cat, _, x, y in points:
            by_family.setdefault(cat, []).append((x, y))
        out = cls(sizes={k: len(v) for k, v in by_family.items()})
        out.families = {k: fit(v) for k, v in by_family.items() if len(v) >= FAMILY_MIN}
        if len(points) >= WORKSPACE_MIN:
            out.workspace = fit([(x, y) for _, _, x, y in points])
        out.floor = warn_floor(warned if warned is not None else [(x, y) for _, m, x, y in points if m])
        return out

    def of(self, f: RawFinding) -> dict[str, Any] | None:
        curve, scope = self.families.get(f.category), f.category
        if curve is None:
            curve, scope = self.workspace, "all"
        if curve is None:
            return None
        return {"agree": round(curve(float(f.confidence)), 3), "n": curve.n, "family": scope}

    def warn_confidence(self, f: RawFinding, default: float, rule: RuleView | None = None) -> float:
        """The floor applies where it was fitted: model-judged findings on should rules."""
        should = rule is not None and rule.severity == "should"
        return self.floor if self.floor is not None and f.model is not None and should else default

    def summary(self) -> dict[str, Any]:
        return {"decisions": self.sizes, "families": sorted(self.families), "workspace": self.workspace is not None,
                "warn_floor": self.floor}


async def load(session: AsyncSession, workspace_id: int, tier: Tier) -> Calibration:
    """Each decided finding's latest decision in the workspace, on content at or below `tier`: even counts
    say how much confidential work there is, so they stay within the tiers this content may cite."""
    last = select(func.max(Decision.id)).group_by(Decision.finding_id).scalar_subquery()
    rows = await session.execute(
        select(Finding.category, Finding.model.is_not(None), Finding.confidence, Decision.action, Decision.reason_code,
               Rule.severity)
        .join(Decision, Decision.finding_id == Finding.id).join(Review, Review.id == Finding.review_id)
        .join(ContentVersion, ContentVersion.id == Review.version_id)
        .join(Content, Content.id == ContentVersion.content_id)
        .outerjoin(Rule, Rule.id == Finding.rule_id)
        .where(Content.workspace_id == workspace_id, Content.tier.in_([t for t in Tier if t.rank <= tier.rank]),
               Decision.id.in_(last))
        .order_by(Decision.id.desc()).limit(MAX_DECISIONS))
    points, warned = [], []
    for cat, modelled, conf, action, reason, severity in rows.all():
        y = agreed(action, reason)
        if y is not None:
            points.append((cat, bool(modelled), float(conf), y))
            if modelled and severity == "should":
                warned.append((float(conf), y))
    return Calibration.from_points(points, warned)
