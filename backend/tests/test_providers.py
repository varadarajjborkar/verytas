from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import respx
from pydantic import BaseModel

from verytas.providers.base import (
    BudgetExceeded,
    ProviderRefusal,
    ProviderUnavailable,
    Question,
    UsageMeter,
)
from verytas.providers.claude import ClaudeLLM, strict_schema
from verytas.providers.jev import JevJudge
from verytas.providers.offline import OfflineJudge

JEV = "https://api.typesafe.test"


def _jev(meter=None, **kw):
    return JevJudge("k", model="jev-1.13.0", base_url=JEV, meter=meter, **kw)


QUESTIONS = {
    "violates": Question("noul", "Does this break VOICE-01?", {"true": "it does", "false": "it does not"}),
    "tone": Question("score", "How on-brand is the tone?", ["off", "ok", "great"]),
    "kind": Question("choice", "What is this?", {"promo": "marketing", "other": "anything else"}),
}

OK_BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "violates": {"type": "noul", "noul": 0.91},
        "tone": {"type": "score", "score": 1.4, "confidence": 0.6, "legend": {}, "probabilities": {"0": 0.1}},
        "kind": {"type": "choice", "choice": "promo", "confidence": 0.8, "probabilities": {"promo": 0.8}},
    },
    "usage": {"input_tokens": 120, "output_tokens": 0},
}


@respx.mock
async def test_jev_parses_typed_answers_and_meters_usage():
    route = respx.post(f"{JEV}/v1/systemone").mock(return_value=httpx.Response(200, json=OK_BODY))
    meter = UsageMeter(budget=10_000)
    answers = await _jev(meter).ask("Some copy", QUESTIONS)

    assert answers["violates"].p_yes == pytest.approx(0.91)
    assert answers["tone"].value == pytest.approx(1.4)
    assert answers["kind"].value == "promo"
    assert meter.total == 120

    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer k"
    body = httpx.Response(200, content=sent.content).json()
    assert body["model"] == "jev-1.13.0"
    assert body["questions"]["tone"] == {"type": "score", "instructions": "How on-brand is the tone?",
                                         "criteria": ["off", "ok", "great"]}
    # Offline-only hints must never leave the process.
    assert "hints" not in body["questions"]["violates"]


@respx.mock
async def test_jev_retries_rate_limits_then_succeeds():
    respx.post(f"{JEV}/v1/systemone").mock(side_effect=[
        httpx.Response(429, headers={"retry-after": "0"}),
        httpx.Response(529),
        httpx.Response(200, json=OK_BODY),
    ])
    answers = await _jev(max_retries=3).ask("x", QUESTIONS)
    assert answers["kind"].value == "promo"


@respx.mock
async def test_jev_does_not_retry_validation_errors():
    route = respx.post(f"{JEV}/v1/systemone").mock(return_value=httpx.Response(422, json={"detail": ["bad"]}))
    with pytest.raises(ProviderUnavailable, match="422"):
        await _jev().ask("x", QUESTIONS)
    assert route.call_count == 1


@respx.mock
async def test_jev_missing_answer_is_an_error_not_a_pass():
    body = {**OK_BODY, "answers": {"violates": OK_BODY["answers"]["violates"]}}
    respx.post(f"{JEV}/v1/systemone").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ProviderUnavailable, match="no answer"):
        await _jev().ask("x", QUESTIONS)


async def test_jev_refuses_oversized_state_instead_of_truncating():
    with pytest.raises(ProviderUnavailable, match="exceeds"):
        await _jev().ask("x" * 200_000, QUESTIONS)


async def test_budget_is_enforced_before_calling():
    meter = UsageMeter(budget=100)
    meter.add("p", 100, 0)
    with pytest.raises(BudgetExceeded):
        await _jev(meter).ask("x", QUESTIONS)


async def test_offline_judge_uses_hints():
    q = Question("noul", "violates?", hints={"yes": ["synergy driven paradigm shift"], "no": ["plain words"]})
    judge = OfflineJudge()
    bad = await judge.ask("A synergy driven paradigm shift for all", {"q": q})
    good = await judge.ask("We use plain words", {"q": q})
    assert bad["q"].p_yes > 0.8 > good["q"].p_yes


class Inner(BaseModel):
    text: str
    note: str | None


class Outer(BaseModel):
    items: list[Inner]
    count: int


def test_strict_schema_inlines_refs_and_closes_objects():
    schema = strict_schema(Outer)
    assert "$defs" not in schema
    item = schema["properties"]["items"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"text", "note"}
    assert schema["required"] == ["items", "count"]


class _Task:
    name = "t"
    system = "sys"
    schema = Outer
    fast = False

    def user_content(self):
        return "hello"

    def heuristic(self):
        return Outer(items=[], count=0)


def _response(stop_reason="end_turn", text='{"items": [{"text": "a", "note": null}], "count": 1}'):
    return SimpleNamespace(
        stop_reason=stop_reason, stop_details=SimpleNamespace(category="cyber"),
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class _FakeAnthropic:
    def __init__(self, response):
        self.calls = []

        async def create(**kw):
            self.calls.append(kw)
            return response

        self.messages = SimpleNamespace(create=create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


async def test_claude_main_model_uses_fallbacks_and_structured_output():
    fake = _FakeAnthropic(_response())
    meter = UsageMeter(budget=1000)
    llm = ClaudeLLM(model="claude-opus-5-5", fast_model="claude-haiku-5-5", meter=meter, client=fake)
    out = await llm.run(_Task())
    assert out.count == 1 and out.items[0].text == "a"
    call = fake.calls[0]
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert meter.total == 15


async def test_claude_fast_tasks_use_fast_model_without_fallbacks():
    fake = _FakeAnthropic(_response())
    task = _Task()
    task.fast = True
    await ClaudeLLM(model="claude-opus-5-5", fast_model="claude-haiku-5-5", client=fake).run(task)
    assert fake.calls[0]["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in fake.calls[0]


async def test_claude_refusal_raises():
    fake = _FakeAnthropic(_response(stop_reason="refusal"))
    with pytest.raises(ProviderRefusal, match="cyber"):
        await ClaudeLLM(model="m", fast_model="f", client=fake).run(_Task())
