from __future__ import annotations

from datetime import date

from verytas.checks.base import CheckContext, FactView, RuleView, TermView
from verytas.checks.system_rules import SYSTEM_RULES
from verytas.ingest.segment import image_units, segment


def system_rule_views() -> list[RuleView]:
    return [
        RuleView(id=i, code=r["code"], category=r["category"], kind=r["kind"], severity=r["severity"],
                 title=r["title"], text=r["text"], pattern=r["pattern"])
        for i, r in enumerate(SYSTEM_RULES, start=1)
    ]


def rule(code: str, pattern: dict, *, category: str = "terminology", kind: str = "deterministic",
         severity: str = "should", text: str = "House style.", rid: int = 100, **kw) -> RuleView:
    return RuleView(id=rid, code=code, category=category, kind=kind, severity=severity, title=code,
                    text=text, pattern=pattern, **kw)


def make_ctx(body: str, rules: list[RuleView] | None = None, *, facts: list[FactView] | None = None,
             terms: list[TermView] | None = None, attachments: dict | None = None,
             today: date = date(2026, 10, 20)) -> CheckContext:
    attachments = attachments or {}
    return CheckContext(
        body=body, units=segment(body) + image_units(attachments), rules=rules or [],
        facts=facts or [], terms=terms or [], attachments=attachments, today=today,
    )
