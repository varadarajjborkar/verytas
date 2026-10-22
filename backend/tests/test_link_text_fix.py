"""Vague link text ("click here") must come with a suggested fix, like other findings.

A good replacement depends on where the link goes, so the fix is the AI's job:
the finding has to reach explain-and-fix with the destination visible.
"""

from __future__ import annotations

from tests.helpers import make_ctx, system_rule_views
from verytas.checks.deterministic import run_deterministic
from verytas.prism.suggest import ExplainAndFixTask, Fix, FixList, explain_and_fix
from verytas.providers.base import Answer

BODY = "Our plans start at $20 a month. To compare them, [click here](https://verytas.example/pricing)."


class EditorLLM:
    """Stand-in for the hosted model: proposes descriptive link text, records what it was shown."""

    name = "stub/llm"

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def run(self, task):
        assert isinstance(task, ExplainAndFixTask)
        self.seen.append(task.user_content())
        return FixList(fixes=[
            Fix(key=key, explanation="'click here' doesn't say where the link goes.",
                original="click here", proposed="compare our pricing plans")
            for key, _, _ in task.items
        ])


class AgreeingJudge:
    name = "stub/judge"

    def __init__(self) -> None:
        self.states: list = []

    async def ask(self, state, questions):
        self.states.append(state)
        return {name: Answer("noul", 0.95) for name in questions}


async def test_models_see_the_sentence_around_the_link():
    # Judged out of context, "[click here](url)" -> "[pricing](url)" looks like a changed call to
    # action and the fix gets dropped; the sentence is what shows the reader's action is the same.
    ctx = make_ctx(BODY, system_rule_views())
    findings = run_deterministic(ctx)
    llm, judge = EditorLLM(), AgreeingJudge()
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, llm, judge)

    assert any("To compare them," in shown for shown in llm.seen)
    original, revised = judge.states[-1]["original"], judge.states[-1]["revised"]
    assert original == "To compare them, [click here](https://verytas.example/pricing)."
    assert revised == "To compare them, [compare our pricing plans](https://verytas.example/pricing)."
    link = _link_finding(findings)
    assert link.quote == "[click here](https://verytas.example/pricing)"  # the highlight stays on the link


def _link_finding(findings):
    return next(f for f in findings if f.rule_code == "A11Y-LINKTEXT")


class FixedProposalLLM:
    """Stand-in that always proposes the given replacement for the link text."""

    name = "stub/llm"

    def __init__(self, proposed: str) -> None:
        self.proposed = proposed

    async def run(self, task):
        return FixList(fixes=[Fix(key=key, explanation="Vague link.", original="click here", proposed=self.proposed)
                              for key, _, _ in task.items])


LEAD_IN = "We help teams publish faster. Read [click here](https://verytas.example)."


async def test_fix_that_repeats_the_word_before_the_link_is_dropped():
    # "Read [click here](...)" -> "Read [Read the article](...)" doubles "Read"; never show that fix.
    ctx = make_ctx(LEAD_IN, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, FixedProposalLLM("Read the article"),
                          AgreeingJudge())
    assert _link_finding(findings).suggestion is None


async def test_fix_that_reads_naturally_in_the_sentence_is_kept():
    ctx = make_ctx(LEAD_IN, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, FixedProposalLLM("the launch article"),
                          AgreeingJudge())
    s = _link_finding(findings).suggestion
    assert s is not None and s.proposed == "the launch article"


class WholeLinkLLM:
    """Stand-in that targets the whole Markdown link, as the live model sometimes does."""

    name = "stub/llm"

    def __init__(self, proposed: str) -> None:
        self.proposed = proposed

    async def run(self, task):
        return FixList(fixes=[Fix(key=key, explanation="Vague link.", original=f.quote, proposed=self.proposed)
                              for key, f, _ in task.items])


async def test_fix_that_drops_the_link_is_dropped():
    # "[click here](url)" -> "the article" removes the link itself: never show that fix.
    ctx = make_ctx(LEAD_IN, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, WholeLinkLLM("the article"), AgreeingJudge())
    assert _link_finding(findings).suggestion is None


async def test_fix_that_rewrites_the_whole_link_but_keeps_it_is_kept():
    ctx = make_ctx(LEAD_IN, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules},
                          WholeLinkLLM("[the launch article](https://verytas.example)"), AgreeingJudge())
    assert _link_finding(findings).suggestion is not None


async def test_repeats_already_in_the_draft_do_not_block_a_fix():
    # Only repeats the fix *introduces* count; the writer's own "very very" isn't the fix's fault.
    body = "It is very very easy. Read [click here](https://verytas.example)."
    ctx = make_ctx(body, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, FixedProposalLLM("the guide"),
                          AgreeingJudge())
    assert _link_finding(findings).suggestion is not None


async def test_vague_link_text_gets_a_suggested_fix():
    ctx = make_ctx(BODY, system_rule_views())
    findings = run_deterministic(ctx)
    llm = EditorLLM()

    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, llm, AgreeingJudge())

    link = _link_finding(findings)
    assert link.suggestion is not None, "vague link text should offer a fix"
    assert (link.suggestion.original, link.suggestion.proposed) == ("click here", "compare our pricing plans")
    # The model needs the destination to write descriptive text.
    assert any("https://verytas.example/pricing" in shown for shown in llm.seen)


async def test_applying_the_link_fix_keeps_the_url():
    ctx = make_ctx(BODY, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, EditorLLM(), AgreeingJudge())

    link = _link_finding(findings)
    # Same rule apply-fixes uses: the original must sit inside the finding's span.
    at = BODY.find(link.suggestion.original, link.span_start, link.span_end)
    fixed = BODY[:at] + link.suggestion.proposed + BODY[at + len(link.suggestion.original):]
    assert fixed == ("Our plans start at $20 a month. To compare them, "
                     "[compare our pricing plans](https://verytas.example/pricing).")


async def test_link_finding_is_still_model_free():
    # Asking the AI for a fix must not turn a plain-code finding into an AI one
    # (that would change its level: AI findings can never block).
    ctx = make_ctx(BODY, system_rule_views())
    findings = run_deterministic(ctx)
    await explain_and_fix(findings, {r.code: r for r in ctx.rules}, EditorLLM(), AgreeingJudge())
    link = _link_finding(findings)
    assert link.model is None and link.confidence == 1.0
