"""Live links and numbers: who records them, what a link must be, sheets of numbers, and when a comparison
between rules says anything at all."""

from __future__ import annotations

import pytest

from tests.test_media import _auth, world  # noqa: F401  (the fixture is used by name)
from verytas.api.results import canonical, engagement, platform_of


def _approved(client, world, body="A calm note about this week's lessons.", tier="public"):  # noqa: F811
    made = client.post("/contents?wait=true", headers=_auth(world["creator"]),
                       json={"title": "Post", "channel": "instagram", "body": body, "tier": tier}).json()
    cid = made["content"]["id"]
    assert client.post(f"/contents/{cid}/transition", headers=_auth(world["creator"]),
                       json={"to": "in_review"}).status_code == 200
    moved = client.post(f"/contents/{cid}/transition", headers=_auth(world["approver"]), json={"to": "approved"})
    assert moved.status_code == 200, moved.text
    return cid


def test_links_are_one_address_whatever_the_share_sheet_added():
    assert canonical("https://www.Instagram.com/p/Cx12/?igsh=abc&utm_source=ig#c") == "https://instagram.com/p/Cx12"
    watch = "https://youtube.com/watch?v=abc"
    for same in ("https://www.youtube.com/watch?v=abc&si=xyz", "https://m.youtube.com/watch?v=abc", "https://youtu.be/abc?si=1",
                 "https://youtube.com/shorts/abc", "https://youtube.com./watch?v=abc"):
        assert canonical(same) == watch, same
    # Parameter order says nothing about the post; a site that isn't a platform keeps its www.
    assert canonical("https://shop.example/p?b=2&a=1") == canonical("https://shop.example/p?a=1&b=2")
    assert canonical("https://www.example.com/a") == "https://www.example.com/a"
    for bad in ("http://instagram.com/p/1", "https://user:pw@x.com/a", "instagram.com/p/1", "javascript:alert(1)",
                "https://insta gram.com/p/1", "https://x.com/" + "a" * 600):
        with pytest.raises(ValueError):
            canonical(bad)
    assert platform_of("https://m.youtube.com/shorts/1") == "youtube"
    assert platform_of("https://notinstagram.com/p/1") == "other"


def test_engagement_is_interactions_per_person_reached():
    assert engagement({"reach": 1000, "likes": 40, "comments": 5, "saves": 5}) == 0.05
    assert engagement({"views": 200, "likes": 10}) == 0.05
    assert engagement({"likes": 10}) is None
    # With a basis, a post without that denominator has no rate rather than one on another scale.
    assert engagement({"views": 200, "likes": 10}, "reach") is None


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


def test_an_auditor_reads_results_and_a_wrong_link_stays_removable(client, world):  # noqa: F811
    auditor = client.post("/users", headers=_auth(world["admin"]),
                          json={"email": "aud@acme.io", "name": "aud", "role": "auditor"}).json()["token"]
    cid = _approved(client, world)
    url = {"url": "https://www.instagram.com/p/Wrong1"}
    assert client.put(f"/contents/{cid}/result", headers=_auth(auditor), json=url).status_code == 403
    assert client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]), json=url).status_code == 200
    assert client.get(f"/contents/{cid}/result", headers=_auth(auditor)).json()["url"].endswith("/p/Wrong1")
    assert client.delete(f"/contents/{cid}/result", headers=_auth(auditor)).status_code == 403
    # Sent back for changes, the piece is no longer live, but the mistaken link can still go.
    back = client.post(f"/contents/{cid}/transition", headers=_auth(world["approver"]),
                       json={"to": "changes_requested", "note": "One more pass."})
    assert back.status_code == 200, back.text
    assert client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]), json=url).status_code == 409
    assert client.delete(f"/contents/{cid}/result", headers=_auth(world["creator"])).status_code == 204


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


def test_a_sheet_from_excel_or_with_odd_cells_is_read_or_skipped_never_a_500(client, world):  # noqa: F811
    cid = _approved(client, world)
    client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]), json={"url": "https://x.com/brand/status/7"})
    reviewer = _auth(world["reviewer"])

    def run(sheet):
        res = client.post("/results/import", headers=reviewer, json={"csv": sheet})
        assert res.status_code == 200, res.text
        return res.json()

    # Excel's byte-order mark and a European semicolon sheet, where 1.000 is a thousand.
    assert run("\ufeffurl;reach;likes\nhttps://x.com/brand/status/7;\"1.000\";10\n")["updated"] == 1
    assert client.get(f"/contents/{cid}/result", headers=reviewer).json()["metrics"]["reach"] == 1000
    # More cells than headers, overflowing and negative numbers: skipped by row, the rest still read.
    out = run("url,reach\n"
              "https://x.com/brand/status/7,500,extra,cells\n"
              "https://x.com/brand/status/7,1e999\n"
              "https://x.com/brand/status/7,-0.5\n"
              "https://x.com/brand/status/7,inf\n")
    assert out["updated"] == 1 and out["skipped_total"] == 3
    assert client.get(f"/contents/{cid}/result", headers=reviewer).json()["metrics"]["reach"] == 500


def test_a_sheet_cannot_reach_a_piece_above_the_importers_clearance(client, world):  # noqa: F811
    cid = _approved(client, world, tier="internal")
    client.put(f"/contents/{cid}/result", headers=_auth(world["creator"]), json={"url": "https://x.com/brand/status/9"})
    low = client.post("/users", headers=_auth(world["admin"]), json={
        "email": "low@acme.io", "name": "low", "role": "reviewer", "clearance": "public"}).json()["token"]
    out = client.post("/results/import", headers=_auth(low),
                      json={"csv": "url,reach\nhttps://x.com/brand/status/9,99\n"}).json()
    assert out["updated"] == 0 and out["skipped"][0]["reason"].startswith("no piece has this link")
    assert client.get(f"/contents/{cid}/result", headers=_auth(world["creator"])).json()["metrics"] == {}


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
