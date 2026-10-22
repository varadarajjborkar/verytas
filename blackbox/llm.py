"""Minimal Ollama Cloud client for the simulator.

Deliberately separate from the backend's providers: the simulator must not
import anything from the system under test, or a bug shared by both sides
would be invisible to it.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

_RETRYABLE = {429, 500, 502, 503, 504}


def load_key() -> str | None:
    """OLLAMA_API_KEY from the environment, else from backend/.env (gitignored)."""
    if key := os.environ.get("OLLAMA_API_KEY"):
        return key
    env = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OLLAMA_API_KEY" and value.strip():
                return value.strip()
    return None


class OllamaChat:
    def __init__(self, api_key: str, *, base_url: str = "https://ollama.com", timeout_s: float = 180.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s,
                                         headers={"Authorization": f"Bearer {api_key}"})
        self.calls = 0
        self.tokens = 0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def json(self, model: str, system: str, user: str, *, temperature: float = 0.9) -> Any:
        """One chat call that must return a JSON value. One repair round."""
        messages = [{"role": "system", "content": system + "\n\nReply with ONLY JSON: no prose, no fences."},
                    {"role": "user", "content": user}]
        body: dict[str, Any] = {"model": model, "stream": False, "options": {"temperature": temperature}}
        if model.startswith("gpt-oss"):
            body["think"] = "low"
        last = ""
        for _ in range(2):
            data = await self._post({**body, "messages": messages})
            reply = (data.get("message") or {}).get("content") or ""
            try:
                return _parse(reply)
            except ValueError as exc:
                last = str(exc)
                messages += [{"role": "assistant", "content": reply},
                             {"role": "user",
                              "content": f"That was not valid JSON ({last}). Reply with only the JSON."}]
        raise RuntimeError(f"{model} never produced valid JSON: {last[:200]}")

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            try:
                res = await self._client.post("/api/chat", json=payload)
            except httpx.HTTPError:
                res = None
            if res is not None and res.status_code == 200:
                data = res.json()
                self.calls += 1
                self.tokens += int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
                return data
            if res is not None and res.status_code not in _RETRYABLE:
                raise RuntimeError(f"Ollama HTTP {res.status_code}: {res.text[:200]}")
            await asyncio.sleep(2.0 * 2**attempt)
        raise RuntimeError("Ollama unavailable after retries")


def _parse(reply: str) -> Any:
    text = reply.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON value found")
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from None
    return value
