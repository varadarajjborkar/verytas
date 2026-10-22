"""Claude client for structured text work (claims, explanations, rewrites).

Uses JSON-schema structured outputs so responses are validated pydantic models,
never free text we have to scrape. The main model runs with server-side refusal
fallbacks enabled, so a policy decline is retried on a fallback model instead
of failing the check.
"""

from __future__ import annotations

from typing import Any

import anthropic
from pydantic import BaseModel

from verytas.providers.base import ProviderRefusal, ProviderUnavailable, StructuredTask, UsageMeter
from verytas.providers.schema import strict_schema

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeLLM:
    def __init__(self, *, model: str, fast_model: str, fallbacks: bool = True,
                 meter: UsageMeter | None = None, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.model = model
        self.fast_model = fast_model
        self.fallbacks = fallbacks
        self.name = f"anthropic/{model}"
        self._meter = meter
        # The SDK already retries 408/409/429/5xx and connection errors with backoff.
        self._client = client or anthropic.AsyncAnthropic(max_retries=3, timeout=90.0)

    def model_for(self, task: StructuredTask[Any]) -> str:
        return self.fast_model if task.fast else self.model

    async def run[T: BaseModel](self, task: StructuredTask[T]) -> T:
        if self._meter:
            self._meter.check()
        model = self.model_for(task)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": 8000,
            "system": task.system,
            "messages": [{"role": "user", "content": task.user_content()}],
            "output_config": {
                "effort": "low" if task.fast else "medium",
                "format": {"type": "json_schema", "schema": strict_schema(task.schema)},
            },
        }
        try:
            if self.fallbacks and model == self.model:
                response = await self._client.beta.messages.create(
                    **request, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = await self._client.messages.create(**request)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderUnavailable(f"Claude auth failed: {exc.message}") from exc
        except anthropic.BadRequestError as exc:
            raise ProviderUnavailable(f"Claude rejected the request: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderUnavailable("Claude rate limit persisted after retries") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderUnavailable(f"Claude HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable("Claude unreachable") from exc
        except anthropic.AnthropicError as exc:
            # Includes missing credentials, which the SDK only reports at request time.
            raise ProviderUnavailable(f"Claude client error: {type(exc).__name__}") from exc

        if self._meter and response.usage:
            self._meter.add(f"anthropic/{model}", response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise ProviderRefusal(f"{task.name}: model declined (category={category})")
        if response.stop_reason == "max_tokens":
            raise ProviderUnavailable(f"{task.name}: output hit max_tokens")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ProviderUnavailable(f"{task.name}: no text block in response")
        return task.schema.model_validate_json(text)
