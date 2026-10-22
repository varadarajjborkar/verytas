"""Context layers: which passes run, and that they run side by side."""

from __future__ import annotations

import asyncio

from tests.helpers import make_ctx, system_rule_views
from verytas.checks.base import Source
from verytas.prism import onion
from verytas.prism.agents import AgentNode, AgentTree, ReviewRun
from verytas.prism.governor import Governor
from verytas.providers.offline import OfflineJudge, OfflineLLM


class _Recorder:
    """A model that answers every layer with nothing, and notes which layers asked and how many at once."""

    name = "recorder"

    def __init__(self) -> None:
        self.layers: list[str] = []
        self.inflight = self.peak = 0

    async def run(self, task):
        self.layers.append(task.layer)
        self.inflight += 1
        self.peak = max(self.peak, self.inflight)
        await asyncio.sleep(0.01)
        self.inflight -= 1
        return task.heuristic()


def _run(body: str, llm: _Recorder, **extra) -> ReviewRun:
    rules = system_rule_views()
    run = ReviewRun(base=make_ctx(body, rules), llm=llm, judge=OfflineJudge(), vision=OfflineLLM(),
                    governor=Governor(4, 10), tree=AgentTree(8, 50), rule_by_code={r.code: r for r in rules},
                    assets=[], content_tier_rank=0, allow_cloud_vision=False, semantic_threshold=0.6,
                    ocr_min_confidence=0.8)
    run.sources.append(Source("body", "body", body, "typed"))
    for k, v in extra.items():
        setattr(run, k, v)
    return run


async def _layers(body: str, **extra) -> _Recorder:
    llm = _Recorder()
    run = _run(body, llm, **extra)
    await onion.onion_agent(run, AgentNode("a1", "context", "Onion", None, 0))
    return llm


async def test_a_short_text_post_is_read_once_as_a_whole():
    llm = await _layers("Learn faster with Kitepath.")
    assert llm.layers == ["document"]


async def test_long_text_also_gets_paragraph_windows_and_they_run_together():
    llm = await _layers("\n\n".join(f"Paragraph {i} about learning." for i in range(7)))
    assert sorted(llm.layers) == ["document", "local"] and llm.peak == 2


async def test_media_or_a_folded_caption_adds_the_cross_modal_read():
    assert "cross_modal" in (await _layers("A caption.", scenes={"img": {"description": "a desk"}})).layers
    assert "cross_modal" in (await _layers("A long caption.", caption_folded=True)).layers
