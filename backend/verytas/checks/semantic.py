"""Semantic rules judged by Jev: one request per paragraph, one question per rule.

Rules with kind="semantic" become `noul` questions ("does this paragraph break
VOICE-03?"). A rule with pattern type "voice_score" becomes a `score` question
over its ordered levels. All questions for a paragraph go in a single parallel
pass, so cost scales with paragraphs, not rules x paragraphs.
"""

from __future__ import annotations

import asyncio

from verytas.checks.base import CheckContext, RawFinding, RuleView
from verytas.providers.base import JudgeProvider, Question

CHECKER = "semantic"
_MAX_EXAMPLES = 3


def _rule_question(rule: RuleView) -> Question:
    yes = "The text clearly breaks this rule."
    no = "The text follows this rule, or the rule does not apply to it."
    if rule.bad_examples:
        yes += " Breaking examples: " + " | ".join(rule.bad_examples[:_MAX_EXAMPLES])
    if rule.good_examples:
        no += " Compliant examples: " + " | ".join(rule.good_examples[:_MAX_EXAMPLES])
    return Question(
        "noul",
        f"Brand rule {rule.code} ({rule.title}): {rule.text} Does the text break this rule?",
        {"true": yes, "false": no},
        hints={"yes": list(rule.bad_examples), "no": list(rule.good_examples)},
    )


def _score_question(rule: RuleView) -> Question:
    return Question("score", f"Brand rule {rule.code}: {rule.text} How well does the text match?",
                    list(rule.pattern["levels"]))


async def check_semantic(ctx: CheckContext, judge: JudgeProvider, *, threshold: float,
                         per_rule: dict[str, float] | None = None) -> list[RawFinding]:
    """`per_rule` holds thresholds learned from disputes and decisions (prism/disputes.py)."""
    noul_rules = [r for r in ctx.rules if r.kind == "semantic" and r.pattern.get("type") != "voice_score"]
    score_rules = [r for r in ctx.rules if r.kind == "semantic" and r.pattern.get("type") == "voice_score"
                   and len(r.pattern.get("levels", [])) >= 2]
    if not (noul_rules or score_rules):
        return []

    questions = {f"rule_{r.id}": _rule_question(r) for r in noul_rules}
    questions |= {f"score_{r.id}": _score_question(r) for r in score_rules}
    by_key = {f"rule_{r.id}": r for r in noul_rules} | {f"score_{r.id}": r for r in score_rules}

    paragraphs = ctx.units_of("paragraph")
    # One failed paragraph fails the check (a partial result would claim coverage
    # it doesn't have), and the calls still in flight are cancelled so they stop
    # spending budget.
    tasks = [asyncio.ensure_future(judge.ask(p.text, questions)) for p in paragraphs]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            t.cancel()
        raise

    findings: list[RawFinding] = []
    for para, answers in zip(paragraphs, results, strict=True):
        for key, answer in answers.items():
            rule = by_key[key]
            if answer.type == "noul" and answer.p_yes >= (per_rule or {}).get(rule.code, threshold):
                confidence = answer.p_yes
                title = f"May break {rule.code}: {rule.title}"
            elif answer.type == "score":
                levels = rule.pattern["levels"]
                # A stored pattern can carry min_level: null; that means "use the midpoint".
                min_level = rule.pattern.get("min_level")
                floor = float(min_level) if min_level is not None else (len(levels) - 1) / 2
                if float(answer.value) >= floor:
                    continue
                # Probability mass below the floor is what we are actually claiming.
                confidence = sum(p for lvl, p in answer.probabilities.items() if int(lvl) < floor) or 0.5
                nearest = levels[max(0, min(len(levels) - 1, round(float(answer.value))))]
                title = f"{rule.title}: reads as '{nearest}'"
            else:
                continue
            findings.append(RawFinding(
                unit_id=para.id, category=rule.category, title=title, explanation=rule.text,
                confidence=round(min(max(confidence, 0.0), 1.0), 4), checker=CHECKER, rule_code=rule.code,
                quote=para.text, span_start=para.start, span_end=para.end, model=judge.name,
                needs_explanation=True,
            ))
    return findings
