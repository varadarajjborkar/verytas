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
from verytas.providers.claude import ClaudeLLM
from verytas.providers.jev import JevJudge
from verytas.providers.offline import OfflineJudge
from verytas.providers.schema import extract_json_object, strict_schema

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


# --- Ollama -------------------------------------------------------------------

from verytas.providers.ollama import OllamaLLM  # noqa: E402

OLLAMA = "https://ollama.test"


def _ollama(**kw):
    return OllamaLLM("k", model="gpt-oss:120b", fast_model="gpt-oss:20b", base_url=OLLAMA, **kw)


def _chat(content, **extra):
    return {"model": "gpt-oss:120b", "message": {"role": "assistant", "content": content},
            "done": True, "prompt_eval_count": 50, "eval_count": 20, **extra}


@pytest.mark.parametrize("reply", [
    '{"items": [], "count": 0}',
    'Sure! ```json\n{"items": [{"text": "a }", "note": null}], "count": 1}\n```',
    'Here you go: {"items": [], "count": 2} hope that helps',
])
def test_extract_json_object_handles_chatty_replies(reply):
    assert Outer.model_validate_json(extract_json_object(reply))


@respx.mock
async def test_ollama_puts_schema_in_prompt_and_meters():
    reply = httpx.Response(200, json=_chat('{"items": [], "count": 3}'))
    route = respx.post(f"{OLLAMA}/api/chat").mock(return_value=reply)
    meter = UsageMeter(budget=1000)
    out = await _ollama(meter=meter).run(_Task())
    assert out.count == 3 and meter.total == 70
    sent = httpx.Response(200, content=route.calls.last.request.content).json()
    assert sent["model"] == "gpt-oss:120b" and sent["think"] == "medium" and sent["stream"] is False
    assert '"additionalProperties": false' in sent["messages"][0]["content"]
    assert route.calls.last.request.headers["authorization"] == "Bearer k"


@respx.mock
async def test_ollama_repairs_invalid_json_once():
    route = respx.post(f"{OLLAMA}/api/chat").mock(side_effect=[
        httpx.Response(200, json=_chat('{"items": "nope"}')),
        httpx.Response(200, json=_chat('{"items": [], "count": 1}')),
    ])
    out = await _ollama().run(_Task())
    assert out.count == 1
    repair_turn = httpx.Response(200, content=route.calls.last.request.content).json()["messages"][-1]
    assert "did not validate" in repair_turn["content"]


@respx.mock
async def test_ollama_gives_up_after_repair_round():
    respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(200, json=_chat("no json here")))
    with pytest.raises(ProviderUnavailable, match="never produced valid JSON"):
        await _ollama().run(_Task())


@respx.mock
async def test_ollama_plan_errors_are_not_retried():
    route = respx.post(f"{OLLAMA}/api/chat").mock(
        return_value=httpx.Response(403, json={"error": "this model is not included in your free usage"}))
    with pytest.raises(ProviderUnavailable, match="403"):
        await _ollama().run(_Task())
    assert route.call_count == 1


@respx.mock
async def test_ollama_fast_tasks_use_fast_model():
    reply = httpx.Response(200, json=_chat('{"items": [], "count": 0}'))
    route = respx.post(f"{OLLAMA}/api/chat").mock(return_value=reply)
    task = _Task()
    task.fast = True
    await _ollama().run(task)
    sent = httpx.Response(200, content=route.calls.last.request.content).json()
    assert sent["model"] == "gpt-oss:20b" and sent["think"] == "low"


@respx.mock
async def test_ollama_moves_to_the_backup_key_when_the_first_is_refused():
    ok = httpx.Response(200, json=_chat('{"items": [], "count": 1}'))

    def answer(request):
        backup = request.headers["authorization"] == "Bearer backup"
        return ok if backup else httpx.Response(401, json={"error": "quota"})

    route = respx.post(f"{OLLAMA}/api/chat").mock(side_effect=answer)
    llm = _ollama(fallback_key="backup")
    assert (await llm.run(_Task())).count == 1
    assert [c.request.headers["authorization"] for c in route.calls] == ["Bearer k", "Bearer backup"]
    # It stays on the backup for a while instead of asking the spent key first every time.
    await llm.run(_Task())
    assert route.calls.last.request.headers["authorization"] == "Bearer backup" and route.call_count == 3


@respx.mock
async def test_ollama_backup_key_also_covers_a_key_stuck_on_rate_limits(monkeypatch):
    import verytas.providers.ollama as ollama_mod

    async def no_wait(_):
        return None

    monkeypatch.setattr(ollama_mod.asyncio, "sleep", no_wait)
    route = respx.post(f"{OLLAMA}/api/chat").mock(side_effect=lambda r: httpx.Response(200, json=_chat(
        '{"items": [], "count": 2}')) if r.headers["authorization"] == "Bearer backup" else httpx.Response(429))
    assert (await _ollama(fallback_key="backup").run(_Task())).count == 2
    assert route.call_count == 4  # three tries on the first key, then the backup
    # Without a backup the old behaviour stands: a 401 is a plain failure.
    with pytest.raises(ProviderUnavailable):
        respx.post(f"{OLLAMA}/api/chat").mock(return_value=httpx.Response(401))
        await _ollama().run(_Task())
