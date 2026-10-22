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
    else:
        judge = OfflineJudge()
        notes.append("TYPESAFE_API_KEY not set: semantic rules use the offline heuristic judge")

    from verytas.providers.claude import ClaudeLLM

    llm = ClaudeLLM(
        model=settings.claude_model, fast_model=settings.claude_fast_model,
        fallbacks=settings.claude_fallbacks, meter=meter,
    )
    return judge, llm, notes
