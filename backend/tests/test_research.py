"""Claim research: web results for unsupported claims, as evidence for the reviewer and never a verdict."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from verytas.checks.base import RawFinding
from verytas.prism.research import DailyCap, brand_name, checkable, english, keep, known_site, query_for, research
from verytas.providers.offline import OfflineJudge
from verytas.providers.websearch import WebResult, _results


class FakeSearch:
    name = "fake/web_search"

    def __init__(self, fail: bool = False, results: list[WebResult] | None = None) -> None:
        self.queries: list[str] = []
        self.fail = fail
        self.results = results

    async def search(self, query: str, max_results: int = 3) -> list[WebResult]:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("down")
        if self.results is not None:
            return self.results
        return [WebResult("Survey of learning apps", "https://www.thehindu.com/survey", "Kitepath was rated the best "
                          "app by students across India in the 2026 survey."),
                WebResult("Something big is coming", "https://en.namu.wiki/w/x",
                          "Kitepath 섬띵 빅 이즈 커밍은 송민경의 노래이다."),
                WebResult("Kitepath Limited - Company Profile", "https://open.endole.co.uk/k", "Kitepath Limited, UK."),
                WebResult("Learning apps in 2026", "https://www.livemint.com/apps", "Recipes for monsoon evenings.")]


def _claim(quote="Rated the best app by students across India"):
    return RawFinding("p1", "claims", "Unsupported superlative claim", "x", 0.8, "claims",
                      rule_code="CLAIM-UNSUPPORTED", quote=quote)


def test_unsupported_claims_get_web_results_and_nothing_else_changes():
    f, other = _claim(), RawFinding("p2", "tone", "t", "x", 0.7, "semantic", rule_code="VOICE-01", quote="q")
    search = FakeSearch()
    log = asyncio.run(research([f, other], search, OfflineJudge(), lambda t: t, "Kitepath", DailyCap(10)))
    assert search.queries == ['"Kitepath" Rated the best app by students across India']
    # The Korean page, the unknown company register and the page that never names the brand are dropped.
    assert [r["site"] for r in f.research] == ["thehindu.com"] and other.research is None
    assert f.level_cap is None and f.confidence == 0.8  # evidence only: the finding itself is untouched
    assert log["searched"][0]["outcome"] == "1 result" and log["searched"][0]["dropped"] == 3


def test_only_claims_a_page_could_confirm_are_searched():
    assert query_for(_claim("Something big is coming"), lambda t: t, "Kitepath") is None
    assert query_for(_claim("Guaranteed results in your board exams with Kitepath."), lambda t: t, "Kitepath") is None
    assert query_for(_claim("Kitepath is the number one app in India"), lambda t: t, "Kitepath") == (
        '"Kitepath" is the number one app in India')
    assert all(checkable(q) for q in ("Loved by 98% of parents", "Rated the best app", "Trusted by a million",
                                      "Award-winning courses", "India's #1 learning app"))
    search = FakeSearch()
    log = asyncio.run(research([_claim("Something big is coming")], search, OfflineJudge(), lambda t: t,
                               "Kitepath", DailyCap(10)))
    assert search.queries == [] and log["skipped"] == 1


def test_results_must_be_english_from_a_known_source_and_about_the_brand():
    assert english("Kitepath was rated the best app") and not english("섬띵 빅 이즈 커밍은 송민경의 노래이다")
    assert not english("【影音】Subverse 2023 活動直播 影片 回顧 精彩 片段")
    assert known_site("timesofindia.indiatimes.com") and known_site("ugc.gov.in") and known_site("iitb.ac.in")
    assert not known_site("open.endole.co.uk") and not known_site("linkedin.com") and not known_site("notreuters.com")
    f = _claim()
    junk = [WebResult("Kitepath Limited", "https://open.endole.co.uk/k", "Kitepath Limited, UK."),
            WebResult("Kitepath", "https://en.namu.wiki/w/x", "섬띵 빅 이즈 커밍은 송민경의 노래이다")]
    log = asyncio.run(research([f], FakeSearch(results=junk), OfflineJudge(), lambda t: t, "Kitepath", DailyCap(10)))
    assert f.research is None
    assert log["searched"][0]["outcome"] == "no result in English from a known source naming Kitepath (2 found)"
    assert log["searched"][0]["dropped"] == 2
    assert not english("Le meilleur cours de programmation en Inde, selon les étudiants et les parents du pays")
    assert english("The best coding school in India, according to students and parents across the country")


def test_the_brand_is_matched_as_people_write_it():
    assert brand_name("Kitepath Learning Pvt. Ltd.") == "Kitepath Learning" and brand_name("Byju\u2019s") == "Byju's"
    page = WebResult("Byju\u2019s: India's once most valuable start-up", "https://www.bbc.co.uk/news/x",
                     "Byju\u2019s ...")
    assert keep(page, "Byju's")
    quoted = '"Kitepath" is the number one app'
    assert query_for(_claim(quoted), lambda t: t, "Kitepath") == quoted
    assert query_for(_claim("Kitepaths are the best"), lambda t: t, "Kitepath") == '"Kitepath" Kitepaths are the best'
    f = _claim()
    search = FakeSearch()
    asyncio.run(research([f], search, OfflineJudge(), lambda t: t, "Kitepath Pvt Ltd", DailyCap(10)))
    assert search.queries == ['"Kitepath" Rated the best app by students across India'] and f.research


def test_teasers_do_not_use_up_the_searches_of_a_review():
    claims = [_claim("Something big is coming"), _claim("Something else is coming"), _claim("Loved by 98% of parents")]
    search = FakeSearch()
    log = asyncio.run(research(claims, search, OfflineJudge(), lambda t: t, None, DailyCap(10), per_review=1))
    assert search.queries == ["Loved by 98% of parents"] and log["skipped"] == 2


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
    assert claims and claims[0]["research"][0]["url"] == "https://www.thehindu.com/survey"
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
