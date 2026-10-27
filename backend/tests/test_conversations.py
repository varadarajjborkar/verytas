"""Conversations between a creator and the brand team, with Inki answering when mentioned."""

from __future__ import annotations

import asyncio
import sqlite3
import time

import pytest

from tests.test_media import _auth, _submit, world  # noqa: F401, the fixture is used by name
from verytas.api.messages import call_provider
from verytas.services.messages import MessageHub, MessageSeal


def _start(client, world, who="creator", other_role="reviewer"):  # noqa: F811
    people = client.get("/conversations/people", headers=_auth(world[who])).json()
    other = next(p for p in people if p["role"] == other_role)
    res = client.post("/conversations", headers=_auth(world[who]), json={"user_id": other["id"]})
    assert res.status_code == 200, res.text
    return res.json()["id"], other


def _send(client, token, cid, **body):
    return client.post(f"/conversations/{cid}/messages", headers=_auth(token), json=body)


def test_each_pair_has_one_conversation_and_only_across_the_two_sides(client, world):  # noqa: F811
    cid, reviewer = _start(client, world)
    again = client.post("/conversations", headers=_auth(world["creator"]), json={"user_id": reviewer["id"]})
    assert again.json()["id"] == cid
    # The reviewer opening it from their side lands in the same conversation.
    people = client.get("/conversations/people", headers=_auth(world["reviewer"])).json()
    creator = next(p for p in people if p["role"] == "creator")
    assert creator["conversation_id"] == cid
    assert {p["role"] for p in people} == {"creator"}
    # Two members of the brand team don't open a conversation here, nor does anyone with themselves.
    approver = next(p for p in client.get("/conversations/people", headers=_auth(world["creator"])).json()
                    if p["role"] == "approver")
    assert client.post("/conversations", headers=_auth(world["reviewer"]),
                       json={"user_id": approver["id"]}).status_code == 404
    assert client.post("/conversations", headers=_auth(world["creator"]),
                       json={"user_id": creator["id"]}).status_code == 404


def test_a_message_arrives_unread_and_is_read_once_seen(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    sent = _send(client, world["creator"], cid, text="Can we talk about the launch caption?", client_id="abc12345")
    assert sent.status_code == 201, sent.text
    # The same send twice (a retry after a dropped connection) is stored once.
    assert _send(client, world["creator"], cid, text="Can we talk about the launch caption?",
                 client_id="abc12345").json()["id"] == sent.json()["id"]
    assert client.get("/conversations/unread", headers=_auth(world["reviewer"])).json() == {"unread": 1}
    assert client.get("/conversations/unread", headers=_auth(world["creator"])).json() == {"unread": 0}
    listed = client.get("/conversations", headers=_auth(world["reviewer"])).json()
    assert listed[0]["last"]["text"] == "Can we talk about the launch caption?" and listed[0]["unread"] == 1
    assert client.post(f"/conversations/{cid}/read", headers=_auth(world["reviewer"]),
                       json={"last_id": sent.json()["id"]}).status_code == 204
    assert client.get("/conversations/unread", headers=_auth(world["reviewer"])).json() == {"unread": 0}
    msgs = client.get(f"/conversations/{cid}/messages", headers=_auth(world["reviewer"])).json()
    assert [m["text"] for m in msgs] == ["Can we talk about the launch caption?"]
    assert client.get(f"/conversations/{cid}/messages", headers=_auth(world["approver"])).status_code == 404


def test_pages_go_back_in_time_and_a_screen_catches_up_after_its_last_id(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    ids = [_send(client, world["creator"], cid, text=f"note {i}").json()["id"] for i in range(5)]
    newest = client.get(f"/conversations/{cid}/messages?limit=2", headers=_auth(world["creator"])).json()
    assert [m["text"] for m in newest] == ["note 3", "note 4"]
    older = client.get(f"/conversations/{cid}/messages?limit=2&before={newest[0]['id']}",
                       headers=_auth(world["creator"])).json()
    assert [m["text"] for m in older] == ["note 1", "note 2"]
    after = client.get(f"/conversations/{cid}/messages?after={ids[2]}", headers=_auth(world["creator"])).json()
    assert [m["text"] for m in after] == ["note 3", "note 4"]


def test_text_is_sealed_in_the_database(client, world, settings):  # noqa: F811
    cid, _ = _start(client, world)
    _send(client, world["creator"], cid, text="The Diwali offer price is still open")
    db = sqlite3.connect(settings.database_url.split("///", 1)[1])
    sealed = db.execute("SELECT sealed FROM messages").fetchone()[0]
    assert "Diwali" not in sealed and sealed.startswith("v1.")
    seal = MessageSeal(settings.keys_dir)
    assert seal.open(cid, sealed) == {"text": "The Diwali offer price is still open"}
    assert seal.open(cid + 1, sealed) is None  # moved into another conversation, it does not open


def test_calls_are_meeting_links_from_known_services_only(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    ok = _send(client, world["reviewer"], cid, call_url="https://meet.google.com/abc-defg-hij")
    assert ok.status_code == 201, ok.text
    assert ok.json()["kind"] == "call" and ok.json()["call"]["provider"] == "Google Meet"
    for bad in ("http://meet.google.com/abc", "https://meet.google.com.evil.io/x", "https://evil.io/meet",
                "https://user:pw@zoom.us/j/1", "javascript:alert(1)"):
        assert _send(client, world["reviewer"], cid, call_url=bad).status_code == 422, bad
    assert call_provider("https://acme.zoom.us/j/123") == "Zoom"
    assert _send(client, world["reviewer"], cid, text="   ").status_code == 422


def test_personal_numbers_stay_out_of_the_conversation(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    res = _send(client, world["creator"], cid, text="just whatsapp me on +91 98765 43210")
    assert res.status_code == 422
    assert client.get(f"/conversations/{cid}/messages", headers=_auth(world["creator"])).json() == []


def test_a_message_can_point_at_the_creators_own_piece_only(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    piece, _ = _submit(client, world, body="Launch post")
    content_id = piece["content"]["id"]
    res = _send(client, world["creator"], cid, text="About this one", content_id=content_id)
    assert res.status_code == 201 and res.json()["piece"]["id"] == content_id
    other = client.post("/users", headers=_auth(world["admin"]),
                        json={"email": "c2@acme.io", "name": "c2", "role": "creator"}).json()["token"]
    people = client.get("/conversations/people", headers=_auth(other)).json()
    cid2 = client.post("/conversations", headers=_auth(other),
                       json={"user_id": next(p["id"] for p in people if p["role"] == "reviewer")}).json()["id"]
    assert _send(client, other, cid2, text="look", content_id=content_id).status_code == 404


def test_inki_answers_when_mentioned(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    piece, _ = _submit(client, world, body="This is a game-changer launch")
    _send(client, world["creator"], cid, text="Which issues are left?", content_id=piece["content"]["id"])
    asked = _send(client, world["reviewer"], cid, text="@Inki what is still open here?")
    assert asked.status_code == 201
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        msgs = client.get(f"/conversations/{cid}/messages", headers=_auth(world["creator"])).json()
        if msgs[-1]["kind"] == "inki":
            break
        time.sleep(0.05)
    reply = msgs[-1]
    assert reply["kind"] == "inki" and reply["sender"] is None
    assert reply["asked_by"]["role"] == "reviewer"
    assert "game-changer" in reply["text"]  # offline, it reads the open issue from the record
    # A plain message doesn't wake it.
    _send(client, world["reviewer"], cid, text="thanks, email inki@acme.io if needed")
    time.sleep(0.2)
    assert client.get(f"/conversations/{cid}/messages", headers=_auth(world["creator"])).json()[-1]["kind"] == "text"


@pytest.mark.parametrize("redis_url", [None])
def test_the_hub_delivers_to_open_screens_without_redis(redis_url):
    async def run():
        hub = MessageHub(redis_url, 50)
        await hub.start()
        async with hub.subscribe(7) as mine, hub.subscribe(8) as theirs:
            await hub.publish([7], {"type": "message", "n": 1})
            assert await asyncio.wait_for(mine.get(), 1) == {"type": "message", "n": 1}
            assert theirs.empty()
        assert hub.mode == "local" and await hub.cached_page(1) == (None, None)
        await hub.close()

    asyncio.run(run())


def test_call_links_that_read_differently_in_a_browser_are_refused():
    for bad in ("https://evil.com\\.zoom.us/j/1", "https://zoom.us:abc/", "https://[::1/", "https://zoom.us:443/j/1",
                "https://meet.google.com /x", "https://ZOOM.us@evil.io/"):
        assert call_provider(bad) is None, bad
    assert call_provider("https://meet.google.com/abc-defg-hij?authuser=0") == "Google Meet"


def test_the_live_stream_opens_message_bodies_only_for_the_screen(client, world):  # noqa: F811
    from verytas.api.messages import _opened

    cid, _ = _start(client, world)
    seal = client.app.state.message_seal
    sealed = seal.seal(cid, {"text": "hello", "call": None})
    event = {"type": "message", "message": {"conversation_id": cid, "text": "", "call": None}, "sealed": sealed}
    assert _opened(seal, dict(event))["message"]["text"] == "hello"
    assert "sealed" not in _opened(seal, dict(event))


def test_a_sender_keeps_unread_what_arrived_before_their_reply(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    _send(client, world["creator"], cid, text="first")
    _send(client, world["reviewer"], cid, text="a reply written before reading")
    assert client.get("/conversations/unread", headers=_auth(world["reviewer"])).json() == {"unread": 1}
