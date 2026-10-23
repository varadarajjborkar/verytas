"""Turns raw findings into levels and a per-category scorecard (architecture 8.1).

Levels:
  blocker  : a must-rule hit with high confidence from a model-free check.
             Model-only signals never block on their own (Jev can be swayed by
             content that claims compliance), they cap at warning.
  warning  : likely an issue, a reviewer should look.
  advisory : low confidence or a stylistic point.
"""

from __future__ import annotations

from dataclasses import dataclass

from verytas.checks.base import RawFinding, RuleView
from verytas.models import Level

CATEGORIES = ("claims", "tone", "terminology", "messaging", "visual", "accessibility", "legal", "confidentiality")
_PENALTY = {Level.blocker: 0.5, Level.warning: 0.2, Level.advisory: 0.05}
WARN_CONFIDENCE = 0.6  # a should rule warns at this certainty; calibration may raise it (prism/calibration.py)


def level_for(finding: RawFinding, rule: RuleView | None, *, blocker_confidence: float,
              warn_confidence: float = WARN_CONFIDENCE) -> Level:
    severity = rule.severity if rule else "should"
    model_free = finding.model is None
    if severity == "must" and model_free and finding.confidence >= blocker_confidence:
        return Level.blocker
    if severity == "must" or (severity == "should" and finding.confidence >= warn_confidence):
        return Level.warning
    return Level.advisory


@dataclass
class Scorecard:
    categories: dict[str, dict]
    overall: float
    blockers: int
    warnings: int
    advisories: int

    def as_dict(self) -> dict:
        return {"categories": self.categories, "overall": self.overall, "blockers": self.blockers,
                "warnings": self.warnings, "advisories": self.advisories}


def scorecard(levelled: list[tuple[RawFinding, Level]], checked: set[str],
              statuses: dict[str, str] | None = None) -> Scorecard:
    cats: dict[str, dict] = {}
    for cat in CATEGORIES:
        items = [(f, lvl) for f, lvl in levelled if f.category == cat]
        penalty = sum(_PENALTY[lvl] * f.confidence for f, lvl in items)
        cats[cat] = {
            "checked": cat in checked,
            "status": (statuses or {}).get(cat, "checked" if cat in checked else "not_checked"),
            "score": round(max(0.0, 1.0 - penalty), 3) if cat in checked else None,
            "findings": len(items),
            "blockers": sum(1 for _, lvl in items if lvl is Level.blocker),
        }
    scored = [c["score"] for c in cats.values() if c["score"] is not None]
    counts = {lvl: sum(1 for _, x in levelled if x is lvl) for lvl in Level}
    return Scorecard(
        categories=cats,
        # The weakest category drives the headline: a perfect tone score should
        # not average away a confidentiality leak.
        overall=round(min(scored), 3) if scored else 0.0,
        blockers=counts[Level.blocker], warnings=counts[Level.warning], advisories=counts[Level.advisory],
    )
