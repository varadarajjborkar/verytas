"""Review history and Ask Verytas threads: what a returning user sees."""

from __future__ import annotations

from tests.test_api_flow import _auth
from tests.test_api_flow import world as world  # noqa: F401, the fixture is used by name

PNG = "data:image/png;base64,iVBORw0KGgo="


def test_chat_threads_are_private_and_round_trip(client, world):
    me, other = _auth(world["creator"]), _auth(world["reviewer"])
    made = client.post("/chats", headers=me, json={"title": "Blockers", "messages": [
        {"role": "user", "content": "How are my posts doing?", "images": [PNG]},
        {"role": "assistant", "content": "root = Stack([])"},
    ]})
    assert made.status_code == 201
    tid = made.json()["id"]
    listed = client.get("/chats", headers=me).json()
    assert [t["id"] for t in listed] == [tid]
    # Marked UTC, so a browser doesn't read it as local time.
    assert listed[0]["updated_at"].endswith(("Z", "+00:00"))
    assert client.get("/chats", headers=other).json() == []
    assert client.get(f"/chats/{tid}", headers=other).status_code == 404
    assert client.put(f"/chats/{tid}", headers=other, json={"title": "x", "messages": []}).status_code == 404

    renamed = client.put(f"/chats/{tid}", headers=me, json={"title": "Renamed", "messages": []})
    assert renamed.json()["title"] == "Renamed" and renamed.json()["messages"] == []
    assert client.delete(f"/chats/{tid}", headers=me).status_code == 204
    assert client.get(f"/chats/{tid}", headers=me).status_code == 404


def test_chat_images_must_be_small_image_data_urls(client, world):
    me = _auth(world["creator"])
    bad = {"role": "user", "content": "x", "images": ["javascript:alert(1)"]}
    assert client.post("/chats", headers=me, json={"title": "t", "messages": [bad]}).status_code == 422
    big = {"role": "user", "content": "x", "images": [PNG + "A" * 700_000]}
    assert client.post("/chats", headers=me, json={"title": "t", "messages": [big]}).status_code == 422


def test_content_list_carries_the_latest_review_and_filters_to_mine(client, world):
    creator, reviewer = _auth(world["creator"]), _auth(world["reviewer"])
    body = {"title": "Launch post", "channel": "linkedin", "body": "Verytas is trusted by 1,000+ teams."}
    assert client.post("/contents?wait=true", headers=creator, json=body).status_code == 201
    assert client.post("/contents?wait=true", headers=reviewer, json={**body, "title": "Theirs"}).status_code == 201

    rows = client.get("/contents?mine=true", headers=creator).json()
    assert [r["title"] for r in rows] == ["Launch post"]
    row = rows[0]
    assert row["version_count"] == 1 and row["updated_at"]
    assert row["latest_review"]["status"] == "done" and row["latest_review"]["blockers"] >= 1
    assert {r["title"] for r in client.get("/contents", headers=creator).json()} == {"Launch post", "Theirs"}


def test_assistant_context_redacts_codenames_and_skips_confidential_content(client, world):
    creator, admin = _auth(world["creator"]), _auth(world["admin"])
    body = {"channel": "linkedin", "body": "Psst, Project Lumen lands next month. Verytas is trusted by 1,000+ teams."}
    post = client.post("/contents?wait=true", headers=creator, json={**body, "title": "Spring launch post"})
    memo = client.post("/contents?wait=true", headers=admin,
                       json={**body, "title": "Board memo", "tier": "confidential"})
    assert post.status_code == memo.status_code == 201, memo.text

    ctx = client.get("/assistant/context", headers=admin, params={"q": "how is my spring launch doing?"}).json()
    text = str(ctx)
    assert "Lumen" not in text, "a codename reached the hosted model's context"
    assert "Board memo" not in text, "confidential-tier content must stay out"
    assert [d["title"] for d in ctx["content_details"]][:1] == ["Spring launch post"]
    detail = ctx["content_details"][0]
    assert detail["versions"][0]["blockers"] >= 1 and detail["open_issues"]
    assert "overview" in ctx and "reach" in ctx["note"]


def test_assistant_context_keeps_workspace_analytics_to_analysts(client, world):
    ctx = client.get("/assistant/context", headers=_auth(world["creator"])).json()
    assert "overview" not in ctx and "analytics" in ctx
