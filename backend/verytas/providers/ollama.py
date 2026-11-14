"""Hosted-model client for structured text work: Ollama Cloud's own API, or any OpenAI-compatible endpoint
(NVIDIA's hosted models since Ollama Cloud's free plan ended).

Ollama's cloud endpoint ignores the `format` JSON-schema field for the models
on the free plan (verified 2026-10-20 against gpt-oss, gemma4, nemotron and
minimax), so the schema goes into the system prompt instead and every reply
is validated with pydantic. One repair round feeds the validation error back
to the model before we give up and mark the check as not run.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from verytas.providers.base import ProviderUnavailable, StructuredTask, UsageMeter
from verytas.providers.schema import extract_json_object, strict_schema

_RETRYABLE = {429, 500, 502, 503, 504}
# Answers that mean this key can't be used right now (bad, out of quota, rate limited): worth the backup key.
_KEY_REFUSED = {401, 402, 403, 429}
# How long the backup key stays in use before the main one is tried again.
_FALLBACK_HOLD_S = 600.0

Api = Literal["ollama", "openai"]


class _Pacer:
    """Spaces request starts so one process stays under an endpoint's per-minute cap. NVIDIA's free tier
    allows about 40 requests a minute for the whole account, and one review fans out to many calls: without
    this they all start at once and most come back 429. Shared by every client of the same endpoint.

    No lock: claiming a slot is a read and a write with no await between them, so on one event loop no other
    task can interleave. A waiter that is cancelled keeps its slot, which only spaces the next call a little
    more than needed."""

    def __init__(self, per_minute: int) -> None:
        self.gap = 60.0 / per_minute
        self._next = 0.0

    async def wait(self) -> None:
        now = time.monotonic()
        start = max(now, self._next)
        self._next = start + self.gap
        if start > now:
            await asyncio.sleep(start - now)


_pacers: dict[str, _Pacer] = {}


def _pacer(base_url: str, per_minute: int) -> _Pacer | None:
    """One pacer per endpoint: the cap is the account's, whichever role is asking."""
    if per_minute <= 0:
        return None
    pacer = _pacers.get(base_url)
    if pacer is None or pacer.gap != 60.0 / per_minute:
        pacer = _pacers[base_url] = _Pacer(per_minute)
    return pacer


class OllamaLLM:
    def __init__(self, api_key: str, *, model: str, fast_model: str, base_url: str = "https://ollama.com",
                 meter: UsageMeter | None = None, timeout_s: float = 120.0, max_retries: int = 2,
                 repair_rounds: int = 1, client: httpx.AsyncClient | None = None,
                 fallback_key: str | None = None, api: Api = "ollama", label: str = "ollama",
                 per_minute: int = 0) -> None:
        self.model = model
        self.fast_model = fast_model
        self.name = f"{label}/{model}"
        self._api = api
        self._label = label
        self._pacer = _pacer(base_url, per_minute)
        self._meter = meter
        self._max_retries = max_retries
        self._repair_rounds = repair_rounds
        # A second account's key, used when the first is refused or out of quota, so a long day of
        # development can't leave the live demo without its models. Back to the first after a while.
        self._keys = [api_key] + ([fallback_key] if fallback_key and fallback_key != api_key else [])
        self._fallback_until = 0.0
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    def model_for(self, task: StructuredTask[Any]) -> str:
        return self.fast_model if task.fast else self.model

    async def run[T: BaseModel](self, task: StructuredTask[T]) -> T:
        if self._meter:
            self._meter.check()
        model = self.model_for(task)
        system = (
            f"{task.system}\n\nReply with ONLY one JSON object: no prose, no markdown fences. "
            f"It must validate against this JSON Schema:\n{json.dumps(strict_schema(task.schema))}"
        )
        user = _openai_user_message if self._api == "openai" else _user_message
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, user(task.user_content())]
        # Tasks are deterministic by default; the judge raises temperature only
        # when it resamples a borderline answer.
        temperature = float(getattr(task, "temperature", 0.0))
        effort = "low" if task.fast else "medium"
        body: dict[str, Any]
        if self._api == "openai":
            body = {"model": model, "stream": False, "temperature": temperature, "max_tokens": 4096}
            if "gpt-oss" in model:
                body["reasoning_effort"] = effort
        else:
            body = {"model": model, "stream": False, "options": {"temperature": temperature}}
            if model.startswith("gpt-oss"):
                # gpt-oss always reasons; keep it short for extraction-style work.
                body["think"] = effort

        last_error = ""
        for _ in range(self._repair_rounds + 1):
            data = await self._post({**body, "messages": messages})
            if self._meter:
                self._meter.add(f"{self._label}/{model}", int(data.get("prompt_eval_count") or 0),
                                int(data.get("eval_count") or 0))
            reply = (data.get("message") or {}).get("content") or ""
            try:
                return task.schema.model_validate_json(extract_json_object(reply))
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:600]
                messages += [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"That reply did not validate: {last_error}\n"
                                                "Reply with only the corrected JSON object."},
                ]
        raise ProviderUnavailable(f"{task.name}: {model} never produced valid JSON ({last_error[:200]})")

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        first = 1 if len(self._keys) > 1 and time.monotonic() < self._fallback_until else 0
        for i in range(first, len(self._keys)):
            try:
                return await self._post_with(self._keys[i], payload, last_key=i == len(self._keys) - 1)
            except _KeyRefused:
                # Only reached with a key still to try: move to it and stay there for a while.
                self._fallback_until = time.monotonic() + _FALLBACK_HOLD_S
        # pragma: no cover - the loop always returns
        raise ProviderUnavailable(f"{self._label} refused every configured key")  # pragma: no cover

    async def _post_with(self, key: str, payload: dict[str, Any], *, last_key: bool) -> dict[str, Any]:
        last = "no attempt made"
        headers = {"Authorization": f"Bearer {key}"}
        path = "chat/completions" if self._api == "openai" else "/api/chat"
        name = self._label
        for attempt in range(self._max_retries + 1):
            if self._pacer:
                await self._pacer.wait()
            try:
                res = await self._client.post(path, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if res.status_code == 200:
                    try:
                        data = res.json()
                    except ValueError as exc:
                        raise ProviderUnavailable(f"{name} returned a non-JSON body: {res.text[:200]}") from exc
                    if not isinstance(data, dict):
                        raise ProviderUnavailable(f"{name} returned JSON that is not an object")
                    if data.get("error"):
                        raise ProviderUnavailable(f"{name} error: {str(data['error'])[:300]}")
                    return _from_openai(data) if self._api == "openai" else data
                if res.status_code in _KEY_REFUSED and res.status_code != 429 and not last_key:
                    raise _KeyRefused
                if res.status_code not in _RETRYABLE:
                    # 401/403 includes "model not in your plan"; retrying won't help.
                    raise ProviderUnavailable(f"{name} HTTP {res.status_code}: {res.text[:300]}")
                last = f"HTTP {res.status_code}"
            if attempt < self._max_retries:
                await asyncio.sleep(_backoff(attempt, res if last == "HTTP 429" else None))
        if last == "HTTP 429" and not last_key:
            raise _KeyRefused  # still rate limited after the retries: this key's quota is likely spent
        raise ProviderUnavailable(f"{name} unavailable after {self._max_retries + 1} attempts ({last})")


class _KeyRefused(Exception):
    """The key in use was refused or stayed rate limited, and another key is configured."""


def _user_message(content: str | list[dict[str, Any]]) -> dict[str, Any]:
    """Accept plain text or Anthropic-style content blocks (text + base64 images)."""
    if isinstance(content, str):
        return {"role": "user", "content": content}
    texts, images = [], []
    for block in content:
        if block.get("type") == "text":
            texts.append(block["text"])
        elif block.get("type") == "image" and block.get("source", {}).get("type") == "base64":
            images.append(block["source"]["data"])
    msg: dict[str, Any] = {"role": "user", "content": "\n".join(texts)}
    if images:
        msg["images"] = images
    return msg


def _openai_user_message(content: str | list[dict[str, Any]]) -> dict[str, Any]:
    """The same input for an OpenAI-compatible endpoint: images travel as data URLs inside the content."""
    if isinstance(content, str):
        return {"role": "user", "content": content}
    parts: list[dict[str, Any]] = []
    for block in content:
        if block.get("type") == "text":
            parts.append({"type": "text", "text": block["text"]})
        elif block.get("type") == "image" and block.get("source", {}).get("type") == "base64":
            src = block["source"]
            url = f"data:{src.get('media_type') or 'image/png'};base64,{src['data']}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return {"role": "user", "content": parts}


def _from_openai(data: dict[str, Any]) -> dict[str, Any]:
    """Reshape a chat-completions reply into the fields run() reads from Ollama's own replies.

    A reply cut off at max_tokens (or one that spent it all reasoning) is a provider failure, not invalid
    JSON: the repair round would ask the same model to do the same thing in the same budget."""
    choices = data.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # some endpoints send content parts even for plain text
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    content = content or ""
    if choice.get("finish_reason") == "length" and not content.rstrip().endswith("}"):
        raise ProviderUnavailable("the model's reply was cut off at its length limit")
    if not choices:
        raise ProviderUnavailable("the endpoint returned no choices")
    usage = data.get("usage") or {}
    return {"message": {"content": content},
            "prompt_eval_count": usage.get("prompt_tokens") or 0, "eval_count": usage.get("completion_tokens") or 0}


def _backoff(attempt: int, rate_limited: httpx.Response | None) -> float:
    """Seconds before the next try. A 429 waits as long as the endpoint asks (capped), otherwise long enough
    for a per-minute window to move; other failures back off 1, 2, 4 s."""
    if rate_limited is not None:
        try:
            return min(max(float(rate_limited.headers.get("retry-after", "")), 1.0), 30.0)
        except ValueError:
            return min(5.0 * 2**attempt, 30.0)
    return min(1.0 * 2**attempt, 10.0)
