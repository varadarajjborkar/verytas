"""Claim research: web results for unsupported claims, as evidence for the reviewer and never a verdict."""

from __future__ import annotations

import asyncio

import httpx

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


def test_only_web_links_survive_from_the_search_api():
    res = httpx.Response(200, json={"results": [
        {"title": "Good", "url": "https://sebi.gov.in/a", "content": "text"},
        {"title": "Bad", "url": "javascript:alert(1)", "content": "x"}, "junk",
        {"title": "Data", "url": "data:text/html,hi", "content": "x"}]})
    assert [r.url for r in _results(res)] == ["https://sebi.gov.in/a"]


def test_a_review_shows_web_results_for_an_unsupported_claim_but_not_on_confidential_work(client):
    search = FakeSearch()
    client.app.state.prism._web = search
    h = {"Authorization": "Bearer " + client.post("/bootstrap", json={
        "workspace_name": "Kitepath", "admin_email": "a@k.io", "admin_name": "Meera"}).json()["token"]}

    def review(body, tier="internal"):
        res = client.post("/contents?wait=true", headers=h, json={"title": "T", "channel": "linkedin", "body": body,
                                                                 "tier": tier})
        return client.get(f"/reviews/{res.json()['review_id']}", headers=h).json()

    rev = review("Kitepath is the number one learning app in India, loved by 98% of parents.")
    claims = [f for f in rev["findings"]
              if f["citations"] and f["citations"][0]["label"].startswith("CLAIM-UNSUPPORTED")]
    assert claims and claims[0]["research"][0]["url"] == "https://example.org/survey"
    assert rev["coverage"]["research"]["provider"] == "fake/web_search"
    searched = len(search.queries)
    secret = review("Kitepath is the number one learning app in India, loved by 98% of parents.", "confidential")
    assert len(search.queries) == searched and secret["coverage"]["research"] is None
