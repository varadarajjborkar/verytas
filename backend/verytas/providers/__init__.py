from __future__ import annotations

from verytas.config import Settings
from verytas.providers.base import JudgeProvider, LLMProvider, UsageMeter
from verytas.providers.offline import OfflineJudge, OfflineLLM


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
    elif settings.ollama_api_key is not None:
        from verytas.providers.ollama_judge import OllamaJudge

        judge = OllamaJudge(
            settings.ollama_api_key.get_secret_value(), model=settings.ollama_judge_model,
            base_url=settings.ollama_base_url, meter=meter, resamples=settings.judge_resamples,
            fallback_key=_fallback(settings),
        )
    else:
        judge = OfflineJudge()
        notes.append("no TYPESAFE_API_KEY or OLLAMA_API_KEY: semantic rules use the offline heuristic judge")

    llm: LLMProvider
    if settings.llm_backend == "claude":
        from verytas.providers.claude import ClaudeLLM

        llm = ClaudeLLM(
            model=settings.claude_model, fast_model=settings.claude_fast_model,
            fallbacks=settings.claude_fallbacks, meter=meter,
        )
    elif settings.ollama_api_key is not None:
        from verytas.providers.ollama import OllamaLLM

        llm = OllamaLLM(
            settings.ollama_api_key.get_secret_value(), model=settings.ollama_model,
            fast_model=settings.ollama_fast_model, base_url=settings.ollama_base_url, meter=meter,
            fallback_key=_fallback(settings),
        )
    else:
        llm = OfflineLLM()
        notes.append("OLLAMA_API_KEY not set: claim extraction and rewrites use offline heuristics")
    return judge, llm, notes


def build_second_judge(settings: Settings, meter: UsageMeter) -> JudgeProvider | None:
    """The larger judge that also answers must-rule questions, or None when there is nothing larger to ask
    (offline, no key, or switched off)."""
    if settings.llm_mode == "offline" or settings.second_look_max == 0 or settings.ollama_api_key is None:
        return None
    from verytas.providers.ollama_judge import OllamaJudge

    return OllamaJudge(settings.ollama_api_key.get_secret_value(), model=settings.second_look_model,
                       base_url=settings.ollama_base_url, meter=meter, resamples=settings.judge_resamples,
                       fallback_key=_fallback(settings))


def build_vision(settings: Settings, meter: UsageMeter) -> tuple[LLMProvider, list[str]]:
    """The model that looks at images. Same interface as the text LLM, so it is
    guarded, budgeted and redacted the same way."""
    if settings.llm_mode == "offline":
        return OfflineLLM(), ["offline mode: images are read by local OCR only"]
    if settings.llm_backend == "claude":
        from verytas.providers.claude import ClaudeLLM

        return ClaudeLLM(model=settings.claude_model, fast_model=settings.claude_model,
                         fallbacks=settings.claude_fallbacks, meter=meter), []
    if settings.ollama_api_key is not None:
        from verytas.providers.ollama import OllamaLLM

        vision = OllamaLLM(settings.ollama_api_key.get_secret_value(), model=settings.ollama_vision_model,
                           fast_model=settings.ollama_vision_model, base_url=settings.ollama_base_url, meter=meter,
                           fallback_key=_fallback(settings))
        vision.name = f"ollama/{settings.ollama_vision_model}"
        return vision, []
    return OfflineLLM(), ["no OLLAMA_API_KEY: images are read by local OCR only, without scene or asset review"]


def _fallback(settings: Settings) -> str | None:
    key = settings.ollama_api_key_fallback
    return key.get_secret_value() if key is not None else None
