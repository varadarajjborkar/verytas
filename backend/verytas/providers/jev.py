"""TypeSafe Jev client (POST /v1/systemone).

Jev answers typed questions about a `state` in one parallel pass and returns
probabilities instead of prose. Known limits we design around (see
docs/architecture.md section 8.1): weak at arithmetic, counting and dates; no
rationale; score values not calibrated between levels; can be swayed by
content that claims to satisfy the rubric.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from verytas.providers.base import Answer, ProviderUnavailable, Question, UsageMeter

# Request limit is 64k tokens with at most 32k of state. We size by characters
# (roughly 4 per token) and refuse rather than truncate: truncation would make
# the judge rule on text it never saw.
_MAX_STATE_CHARS = 30_000 * 4
_RETRYABLE = {429, 500, 502, 503, 504, 529}


class JevJudge:
    def __init__(self, api_key: str, *, model: str, base_url: str = "https://api.typesafe.ai",
                 meter: UsageMeter | None = None, timeout_s: float = 30.0, max_retries: int = 3,
                 client: httpx.AsyncClient | None = None) -> None:
        self.model = model
        self.name = f"typesafe/{model}"
        self._meter = meter
        self._max_retries = max_retries
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ask(self, state: str | dict[str, Any], questions: dict[str, Question]) -> dict[str, Answer]:
        if not questions:
            return {}
        size = len(state) if isinstance(state, str) else len(json.dumps(state))
        if size > _MAX_STATE_CHARS:
            raise ProviderUnavailable(f"state of {size} chars exceeds Jev's limit; split the unit first")
        if self._meter:
            self._meter.check()

        payload = {
            "model": self.model,
            "state": state,
            "questions": {name: q.to_api() for name, q in questions.items()},
        }
        data = await self._post(payload)

        usage = data.get("usage") or {}
        if self._meter:
            self._meter.add(self.name, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))

        answers = data.get("answers") or {}
        missing = set(questions) - set(answers)
        if missing:
            raise ProviderUnavailable(f"Jev returned no answer for {sorted(missing)}")
        return {name: _parse_answer(answers[name]) for name in questions}

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error = "no attempt made"
        for attempt in range(self._max_retries + 1):
            try:
                res = await self._client.post("/v1/systemone", json=payload)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if res.status_code == 200:
                    return res.json()
                if res.status_code not in _RETRYABLE:
                    # 401/403/422 won't get better on retry. Surface the detail
                    # (validation errors name the bad field) without the key.
                    raise ProviderUnavailable(f"Jev HTTP {res.status_code}: {res.text[:300]}")
                last_error = f"HTTP {res.status_code}"
                retry_after = res.headers.get("retry-after")
                if retry_after and retry_after.replace(".", "", 1).isdigit() and attempt < self._max_retries:
                    await asyncio.sleep(min(float(retry_after), 20.0))
                    continue
            if attempt < self._max_retries:
                await asyncio.sleep(min(0.5 * 2**attempt, 8.0))
        raise ProviderUnavailable(f"Jev unavailable after {self._max_retries + 1} attempts ({last_error})")


def _parse_answer(raw: dict[str, Any]) -> Answer:
    kind = raw.get("type")
    probs = {str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()}
    if kind == "noul":
        return Answer("noul", float(raw["noul"]), None, probs)
    if kind == "score":
        return Answer("score", float(raw["score"]), _opt_float(raw.get("confidence")), probs)
    if kind == "choice":
        return Answer("choice", str(raw["choice"]), _opt_float(raw.get("confidence")), probs)
    raise ProviderUnavailable(f"unexpected Jev answer type {kind!r}")


def _opt_float(v: Any) -> float | None:
    return None if v is None else float(v)
