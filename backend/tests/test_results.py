"""Live links and numbers: who records them, what a link must be, sheets of numbers, and when a comparison
between rules says anything at all."""

from __future__ import annotations

import pytest

from tests.test_media import _auth, world  # noqa: F401  (the fixture is used by name)
from verytas.api.results import canonical, engagement, platform_of


def _approved(client, world, body="A calm note about this week's lessons."):  # noqa: F811
    made = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                       json={"title": "Post", "channel": "instagram", "body": body}).json()
    cid = made["content"]["id"]
    assert client.post(f"/contents/{cid}/transition", headers=_auth(world["creator"]),
                       json={"to": "in_review"}).status_code == 200
    moved = client.post(f"/contents/{cid}/transition", headers=_auth(world["approver"]), json={"to": "approved"})
    assert moved.status_code == 200, moved.text
    return cid


def test_links_are_one_address_whatever_the_share_sheet_added():
    assert canonical("https://www.Instagram.com/p/Cx12/?igsh=abc&utm_source=ig#c") == "https://www.instagram.com/p/Cx12"
    assert canonical("https://www.youtube.com/watch?v=abc&si=xyz") == "https://www.youtube.com/watch?v=abc"
    for bad in ("http://instagram.com/p/1", "https://user:pw@x.com/a", "instagram.com/p/1", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            canonical(bad)
    assert platform_of("https://m.youtube.com/shorts/1") == "youtube"
    assert platform_of("https://notinstagram.com/p/1") == "other"


def test_engagement_is_interactions_per_person_reached():
    assert engagement({"reach": 1000, "likes": 40, "comments": 5, "saves": 5}) == 0.05
    assert engagement({"views": 200, "likes": 10}) == 0.05
    assert engagement({"likes": 10}) is None


def test_a_creator_records_the_live_link_of_an_approved_piece(client, world):  # noqa: F811
    cid = _approved(client, world)
    put = client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]),
                     json={"url": "https://www.instagram.com/p/Abc123/?igsh=zz", "posted_on": "2026-10-27",
                           "metrics": {"reach": 1200, "likes": 60, "comments": 6}})
    assert put.status_code == 200, put.text
    got = client.get(f"/contents/{cid}/result", headers=_auth(world["reviewer"])).json()
    assert got["platform"] == "instagram" and got["url"].endswith("/p/Abc123") and got["engagement_rate"] == 0.055
    # Recording again replaces it; removing it leaves none.
    assert client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]),
                      json={"url": "https://www.instagram.com/p/Abc123/"}).json()["metrics"] == {}
    assert client.delete(f"/contents/{cid}/result", headers=_auth(world["creator"])).status_code == 204
    assert client.get(f"/contents/{cid}/result", headers=_auth(world["creator"])).json() is None


def test_only_a_cleared_piece_can_have_gone_live_and_a_link_is_one_piece(client, world):  # noqa: F811
    draft = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                        json={"title": "Draft", "body": "Not yet approved."}).json()["content"]["id"]
    refused = client.put(f"/contents/{draft}/result", headers=_auth(world["creator"]),
                         json={"url": "https://x.com/brand/status/1"})
    assert refused.status_code == 409
    one, two = _approved(client, world), _approved(client, world, body="Another calm note.")
    url = {"url": "https://x.com/brand/status/42"}
    assert client.put(f"/contents/{one}/result", headers=_auth(world["creator"]), json=url).status_code == 200
    assert client.put(f"/contents/{two}/result", headers=_auth(world["creator"]), json=url).status_code == 409


def test_a_sheet_of_numbers_updates_results_by_link(client, world):  # noqa: F811
    cid = _approved(client, world)
    client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]),
               json={"url": "https://www.linkedin.com/posts/brand_123"})
    sheet = ("URL,Reach,Likes,Comments\n"
             "https://www.linkedin.com/posts/brand_123?utm_source=share,\"2,400\",90,12\n"
             "https://www.linkedin.com/posts/unknown,10,1,0\n"
             "not a link,1,1,1\n")
    res = client.post("/results/import", headers=_auth(world["reviewer"]), json={"csv": sheet})
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1 and len(res.json()["skipped"]) == 2
    got = client.get(f"/contents/{cid}/result", headers=_auth(world["creator"])).json()
    assert got["metrics"] == {"reach": 2400, "likes": 90, "comments": 12} and got["source"] == "csv"
    # Creators record their own links; importing the brand's numbers is the brand team's.
    assert client.post("/results/import", headers=_auth(world["creator"]), json={"csv": sheet}).status_code == 403
    assert client.post("/results/import", headers=_auth(world["reviewer"]),
                       json={"csv": "link,reach\nx,1\n"}).status_code == 422


def _approved_over(client, world, body):  # noqa: F811
    """Approved although its review found something: the approver overrides with a reason."""
    cid = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                      json={"title": "Post", "channel": "instagram", "body": body}).json()["content"]["id"]
    client.post(f"/contents/{cid}/transition", headers=_auth(world["creator"]), json={"to": "in_review"})
    moved = client.post(f"/contents/{cid}/transition", headers=_auth(world["approver"]),
                        json={"to": "approved", "override_blockers": True, "note": "Cleared with legal for this run."})
    assert moved.status_code == 200, moved.text
    return cid


def test_a_rule_comparison_waits_for_enough_posts_on_both_sides(client, world):  # noqa: F811
    def live(cid, n, likes):
        client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]),
                   json={"url": f"https://www.instagram.com/p/{n}", "metrics": {"reach": 1000, "likes": likes}})

    for i in range(3):
        live(_approved(client, world, body=f"Plain update number {i}."), f"clean{i}", 50 + i)
    for i in range(5):
        live(_approved_over(client, world, body=f"A game-changer of a week, part {i}."), f"hype{i}", 20 + i)
    early = client.get("/insights/performance", headers=_auth(world["reviewer"])).json()
    hype = next(r for r in early["rules"] if r["code"] == "TERM-01")
    assert (hype["needed"], hype["clean"]) == (5, 3) and "difference_90" not in hype

    for i in range(3, 5):
        live(_approved(client, world, body=f"Plain update number {i}."), f"clean{i}", 50 + i)
    report = client.get("/insights/performance", headers=_auth(world["reviewer"])).json()
    hype = next(r for r in report["rules"] if r["code"] == "TERM-01")
    assert report["with_numbers"] == 10 and (hype["needed"], hype["clean"]) == (5, 5)
    assert hype["median_needed"] == 0.022 and hype["median_clean"] == 0.052
    lo, hi = hype["difference_90"]
    assert lo <= hi < 0
    assert client.get("/insights/performance", headers=_auth(world["creator"])).status_code == 403
