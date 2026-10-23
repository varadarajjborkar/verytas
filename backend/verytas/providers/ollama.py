"""Ollama Cloud client for structured text work.

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
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from verytas.providers.base import ProviderUnavailable, StructuredTask, UsageMeter
from verytas.providers.schema import extract_json_object, strict_schema

_RETRYABLE = {429, 500, 502, 503, 504}
# Answers that mean this key can't be used right now (bad, out of quota, rate limited): worth the backup key.
_KEY_REFUSED = {401, 402, 403, 429}
# How long the backup key stays in use before the main one is tried again.
_FALLBACK_HOLD_S = 600.0


class OllamaLLM:
    def __init__(self, api_key: str, *, model: str, fast_model: str, base_url: str = "https://ollama.com",
                 meter: UsageMeter | None = None, timeout_s: float = 120.0, max_retries: int = 2,
                 repair_rounds: int = 1, client: httpx.AsyncClient | None = None,
                 fallback_key: str | None = None) -> None:
        self.model = model
        self.fast_model = fast_model
        self.name = f"ollama/{model}"
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
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, _user_message(task.user_content())]
        # Tasks are deterministic by default; the judge raises temperature only
        # when it resamples a borderline answer.
        temperature = float(getattr(task, "temperature", 0.0))
        body: dict[str, Any] = {"model": model, "stream": False, "options": {"temperature": temperature}}
        if model.startswith("gpt-oss"):
            # gpt-oss always reasons; keep it short for extraction-style work.
            body["think"] = "low" if task.fast else "medium"

        last_error = ""
        for _ in range(self._repair_rounds + 1):
            data = await self._post({**body, "messages": messages})
            if self._meter:
                self._meter.add(f"ollama/{model}", int(data.get("prompt_eval_count") or 0),
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
        raise ProviderUnavailable("Ollama refused every configured key")  # pragma: no cover - loop always returns

    async def _post_with(self, key: str, payload: dict[str, Any], *, last_key: bool) -> dict[str, Any]:
        last = "no attempt made"
        headers = {"Authorization": f"Bearer {key}"}
        for attempt in range(self._max_retries + 1):
            try:
                res = await self._client.post("/api/chat", json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if res.status_code == 200:
                    try:
                        data = res.json()
                    except ValueError as exc:
                        raise ProviderUnavailable(f"Ollama returned a non-JSON body: {res.text[:200]}") from exc
                    if not isinstance(data, dict):
                        raise ProviderUnavailable("Ollama returned JSON that is not an object")
                    if data.get("error"):
                        raise ProviderUnavailable(f"Ollama error: {data['error'][:300]}")
                    return data
                if res.status_code in _KEY_REFUSED and res.status_code != 429 and not last_key:
                    raise _KeyRefused
                if res.status_code not in _RETRYABLE:
                    # 401/403 includes "model not in your plan"; retrying won't help.
                    raise ProviderUnavailable(f"Ollama HTTP {res.status_code}: {res.text[:300]}")
                last = f"HTTP {res.status_code}"
            if attempt < self._max_retries:
                await asyncio.sleep(min(1.0 * 2**attempt, 10.0))
        if last == "HTTP 429" and not last_key:
            raise _KeyRefused  # still rate limited after the retries: this key's quota is likely spent
        raise ProviderUnavailable(f"Ollama unavailable after {self._max_retries + 1} attempts ({last})")


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
