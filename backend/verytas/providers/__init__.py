from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from verytas.config import Settings
from verytas.providers.base import JudgeProvider, LLMProvider, UsageMeter
from verytas.providers.offline import OfflineJudge, OfflineLLM
from verytas.providers.websearch import OllamaWebSearch


def build_providers(settings: Settings, meter: UsageMeter) -> tuple[JudgeProvider, LLMProvider, list[str]]:
    """Pick live or offline providers. Returns notes explaining any downgrade,
    which end up in the review's coverage so nobody mistakes offline for live."""
    if settings.llm_mode == "offline":
        return OfflineJudge(), OfflineLLM(), ["offline mode: heuristic judge and LLM stand-ins"]

    notes: list[str] = []
    judge: JudgeProvider
    if settings.typesafe_api_key is not None:
        from verytas.providers.jev import JevJudge

        judge = JevJudge(
            settings.typesafe_api_key.get_secret_value(), model=settings.jev_model,
            base_url=settings.jev_base_url, meter=meter,
        )
    elif (hosted := _hosted(settings)) is not None:
        judge = _judge(hosted, hosted.judge_model, settings, meter)
    else:
        judge = OfflineJudge()
        notes.append(f"no TYPESAFE_API_KEY or {_key_name(settings)}: semantic rules use the offline heuristic judge")

    llm: LLMProvider
    if settings.llm_backend == "claude":
        from verytas.providers.claude import ClaudeLLM

        llm = ClaudeLLM(
            model=settings.claude_model, fast_model=settings.claude_fast_model,
            fallbacks=settings.claude_fallbacks, meter=meter,
        )
    elif (hosted := _hosted(settings)) is not None:
        llm = _client(hosted, hosted.model, hosted.fast_model, meter)
    else:
        llm = OfflineLLM()
        notes.append(f"{_key_name(settings)} not set: claim extraction and rewrites use offline heuristics")
    return judge, llm, notes


def build_second_judge(settings: Settings, meter: UsageMeter) -> JudgeProvider | None:
    """The larger judge that also answers must-rule questions, or None when there is nothing larger to ask
    (offline, no key, or switched off)."""
    hosted = _hosted(settings)
    if settings.llm_mode == "offline" or settings.second_look_max == 0 or hosted is None:
        return None
    return _judge(hosted, hosted.second_look_model, settings, meter)


def build_vision(settings: Settings, meter: UsageMeter) -> tuple[LLMProvider, list[str]]:
    """The model that looks at images. Same interface as the text LLM, so it is
    guarded, budgeted and redacted the same way."""
    if settings.llm_mode == "offline":
        return OfflineLLM(), ["offline mode: images are read by local OCR only"]
    if settings.llm_backend == "claude":
        from verytas.providers.claude import ClaudeLLM

        return ClaudeLLM(model=settings.claude_model, fast_model=settings.claude_model,
                         fallbacks=settings.claude_fallbacks, meter=meter), []
    if (hosted := _hosted(settings)) is not None:
        return _client(hosted, hosted.vision_model, hosted.vision_model, meter), []
    return OfflineLLM(), [f"no {_key_name(settings)}: images are read by local OCR only, without scene or asset review"]


def build_web_search(settings: Settings) -> OllamaWebSearch | None:
    """Ollama's web search for claim research, or None when offline, keyless, switched off, or on a backend
    without a search API (NVIDIA has none, so claims no fact backs are left for the reviewer, as they say)."""
    if (settings.llm_mode == "offline" or settings.research_per_review == 0 or settings.ollama_api_key is None
            or settings.llm_backend != "ollama"):
        return None
    return OllamaWebSearch(settings.ollama_api_key.get_secret_value(), base_url=settings.ollama_base_url,
                           fallback_key=_fallback(settings))


def _fallback(settings: Settings) -> str | None:
    key = settings.ollama_api_key_fallback
    return key.get_secret_value() if key is not None else None


@dataclass(frozen=True)
class _Hosted:
    """One hosted endpoint and the models each role uses on it."""
    key: str
    base_url: str
    api: Literal["ollama", "openai"]
    label: str
    per_minute: int
    fallback: str | None
    model: str
    fast_model: str
    judge_model: str
    second_look_model: str
    vision_model: str


def _hosted(settings: Settings) -> _Hosted | None:
    if settings.llm_backend == "nvidia":
        if settings.nvidia_api_key is None:
            return None
        return _Hosted(settings.nvidia_api_key.get_secret_value(), settings.nvidia_base_url, "openai", "nvidia",
                       settings.nvidia_per_minute, None, settings.nvidia_model, settings.nvidia_fast_model,
                       settings.nvidia_judge_model, settings.nvidia_second_look_model, settings.nvidia_vision_model)
    if settings.ollama_api_key is None:
        return None
    return _Hosted(settings.ollama_api_key.get_secret_value(), settings.ollama_base_url, "ollama", "ollama", 0,
                   _fallback(settings), settings.ollama_model, settings.ollama_fast_model,
                   settings.ollama_judge_model, settings.second_look_model, settings.ollama_vision_model)


def _client(h: _Hosted, model: str, fast_model: str, meter: UsageMeter):
    from verytas.providers.ollama import OllamaLLM

    return OllamaLLM(h.key, model=model, fast_model=fast_model, base_url=h.base_url, meter=meter,
                     fallback_key=h.fallback, api=h.api, label=h.label, per_minute=h.per_minute)


def _judge(h: _Hosted, model: str, settings: Settings, meter: UsageMeter) -> JudgeProvider:
    from verytas.providers.ollama_judge import OllamaJudge

    return OllamaJudge(h.key, model=model, meter=meter, resamples=settings.judge_resamples, label=h.label,
                       llm=_client(h, model, model, meter))


def _key_name(settings: Settings) -> str:
    return "NVIDIA_API_KEY" if settings.llm_backend == "nvidia" else "OLLAMA_API_KEY"
