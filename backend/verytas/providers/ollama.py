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
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from verytas.providers.base import ProviderUnavailable, StructuredTask, UsageMeter
from verytas.providers.schema import extract_json_object, strict_schema

_RETRYABLE = {429, 500, 502, 503, 504}


class OllamaLLM:
    def __init__(self, api_key: str, *, model: str, fast_model: str, base_url: str = "https://ollama.com",
                 meter: UsageMeter | None = None, timeout_s: float = 120.0, max_retries: int = 2,
                 repair_rounds: int = 1, client: httpx.AsyncClient | None = None) -> None:
        self.model = model
        self.fast_model = fast_model
        self.name = f"ollama/{model}"
        self._meter = meter
        self._max_retries = max_retries
        self._repair_rounds = repair_rounds
        self._client = client or httpx.AsyncClient(
            base_url=base_url, timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"},
        )

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
        last = "no attempt made"
        for attempt in range(self._max_retries + 1):
            try:
                res = await self._client.post("/api/chat", json=payload)
            except httpx.HTTPError as exc:
                last = f"{type(exc).__name__}: {exc}"
            else:
                if res.status_code == 200:
                    data = res.json()
                    if data.get("error"):
                        raise ProviderUnavailable(f"Ollama error: {data['error'][:300]}")
                    return data
                if res.status_code not in _RETRYABLE:
                    # 401/403 includes "model not in your plan"; retrying won't help.
                    raise ProviderUnavailable(f"Ollama HTTP {res.status_code}: {res.text[:300]}")
                last = f"HTTP {res.status_code}"
            if attempt < self._max_retries:
                await asyncio.sleep(min(1.0 * 2**attempt, 10.0))
        raise ProviderUnavailable(f"Ollama unavailable after {self._max_retries + 1} attempts ({last})")


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
