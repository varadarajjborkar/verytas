"""Claim research: web results for unsupported claims, as evidence for the reviewer and never a verdict."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from verytas.checks.base import RawFinding
from verytas.prism.research import DailyCap, query_for, research
from verytas.providers.offline import OfflineJudge
from verytas.providers.websearch import WebResult, _results


class FakeSearch:
    name = "fake/web_search"

    def __init__(self, fail: bool = False) -> None:
        self.queries: list[str] = []
        self.fail = fail

    async def search(self, query: str, max_results: int = 3) -> list[WebResult]:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("down")
        return [WebResult("Survey of learning apps", "https://example.org/survey", "Kitepath was rated the best "
                          "app by students across India in the 2026 survey."),
                WebResult("Unrelated", "https://example.org/other", "Recipes for monsoon evenings.")]


def _claim(quote="Rated the best app by students across India"):
    return RawFinding("p1", "claims", "Unsupported superlative claim", "x", 0.8, "claims",
                      rule_code="CLAIM-UNSUPPORTED", quote=quote)


def test_unsupported_claims_get_web_results_and_nothing_else_changes():
    f, other = _claim(), RawFinding("p2", "tone", "t", "x", 0.7, "semantic", rule_code="VOICE-01", quote="q")
    search = FakeSearch()
    log = asyncio.run(research([f, other], search, OfflineJudge(), lambda t: t, "Kitepath", DailyCap(10)))
    assert search.queries == ["Kitepath Rated the best app by students across India"]
    assert [r["site"] for r in f.research] == ["example.org", "example.org"] and other.research is None
    assert f.level_cap is None and f.confidence == 0.8  # evidence only: the finding itself is untouched
    assert log["searched"][0]["outcome"] == "2 results"


def test_codenames_are_never_searched_and_limits_hold():
    mask = lambda t: t.replace("Falcon", "[confidential]")  # noqa: E731
    assert query_for(_claim("Falcon is the fastest app in India"), mask, "Kitepath") is None
    assert query_for(_claim("ok"), mask, None) is None  # too short to mean anything
    cap = DailyCap(1)
    claims = [_claim(), _claim("Trusted by a million parents across India")]
    log = asyncio.run(research(claims, FakeSearch(), OfflineJudge(), lambda t: t, None, cap))
    assert sorted(e["outcome"] for e in log["searched"]) == ["2 results", "daily limit reached"]
    failed = _claim()
    log = asyncio.run(research([failed], FakeSearch(fail=True), OfflineJudge(), lambda t: t, None, DailyCap(5)))
    assert log["searched"][0]["outcome"].startswith("search failed") and failed.research is None


def test_one_workspace_cannot_use_up_the_allowance_of_the_others():
    cap = DailyCap(per_day=10, per_workspace=2)
    assert [cap.take(1), cap.take(1), cap.take(1)] == [None, None, "this workspace's daily limit reached"]
    assert cap.take(2) is None  # another workspace still has its share
    ceiling = DailyCap(per_day=1, per_workspace=5)
    assert ceiling.take(1) is None and ceiling.take(2) == "daily limit reached"
    claims = [_claim(), _claim("Trusted by a million parents across India")]
    log = asyncio.run(research(claims, FakeSearch(), OfflineJudge(), lambda t: t, None,
                               DailyCap(10, per_workspace=1), workspace=7))
    assert sorted(e["outcome"] for e in log["searched"]) == ["2 results", "this workspace's daily limit reached"]


class SlowSearch(FakeSearch):
    async def search(self, query: str, max_results: int = 3) -> list[WebResult]:
        if self.queries:  # the first claim answers, the second never does
            self.queries.append(query)
            await asyncio.sleep(10)
        return await super().search(query, max_results)


def test_a_timeout_still_lists_every_search_that_was_started():
    f1, f2 = _claim(), _claim("Trusted by a million parents across India")
    log: dict = {}
    with pytest.raises(TimeoutError):
        asyncio.run(asyncio.wait_for(research([f1, f2], SlowSearch(), OfflineJudge(), lambda t: t, None, DailyCap(10),
                                              log=log), timeout=0.5))
    assert f1.research and f2.research is None
    assert sorted(e["outcome"] for e in log["searched"]) == ["2 results", "timed out"]


def test_only_web_links_survive_from_the_search_api():
    res = httpx.Response(200, json={"results": [
        {"title": "Good", "url": "https://sebi.gov.in/a", "content": "text"},
        {"title": "Bad", "url": "javascript:alert(1)", "content": "x"}, "junk",
        {"title": "Data", "url": "data:text/html,hi", "content": "x"},
        {"title": "No host", "url": "https:foo", "content": "x"},
        {"title": "Disguised", "url": "https://apple.com@evil.example/page", "content": "x"},
        {"title": "Broken", "url": "http://[::1/x", "content": "x"}]})
    assert [r.url for r in _results(res)] == ["https://sebi.gov.in/a"]


def test_the_site_name_is_the_host_alone():
    assert WebResult("t", "https://www.example.org:8443/a?x=1", "").site == "example.org"


def test_a_review_shows_web_results_for_an_unsupported_claim_but_only_on_public_work(client):
    search = FakeSearch()
    client.app.state.prism._web = search
    h = {"Authorization": "Bearer " + client.post("/bootstrap", json={
        "workspace_name": "Kitepath", "admin_email": "a@k.io", "admin_name": "Meera"}).json()["token"]}

    def review(body, tier="internal"):
        res = client.post("/contents?wait=true", headers=h, json={"title": "T", "channel": "linkedin", "body": body,
                                                                 "tier": tier})
        return client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()

    rev = review("Kitepath is the number one learning app in India, loved by 98% of parents.", "public")
    claims = [f for f in rev["findings"]
              if f["citations"] and f["citations"][0]["label"].startswith("CLAIM-UNSUPPORTED")]
    assert claims and claims[0]["research"][0]["url"] == "https://example.org/survey"
    assert rev["coverage"]["research"]["provider"] == "fake/web_search"
    searched = len(search.queries)
    for tier in ("internal", "confidential"):
        private = review("Kitepath is the number one learning app in India, loved by 98% of parents.", tier)
        assert len(search.queries) == searched and private["coverage"]["research"] is None


def test_a_research_error_is_recorded_and_never_fails_the_review(client, monkeypatch):
    from types import SimpleNamespace

    from verytas.prism import research as module

    async def boom(*args, **kwargs):
        raise RuntimeError("search stack fell over")

    prism = client.app.state.prism
    prism._web = FakeSearch()
    monkeypatch.setattr(module, "research", boom)
    log = asyncio.run(prism._research([], OfflineJudge(), SimpleNamespace(mask=lambda t: t), "Kitepath", 1))
    assert log["note"] == "failed: RuntimeError" and log["searched"] == []
