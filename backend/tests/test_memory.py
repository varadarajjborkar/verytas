"""Inki's memory: earlier turns of a long conversation recalled by meaning, kept sealed at rest."""

from __future__ import annotations

import time
from types import SimpleNamespace

from tests.test_conversations import _send, _start
from tests.test_media import _auth, world  # noqa: F401  (the fixture is used by name)
from verytas.models import MessageVector

FILLER = ["ok", "sounds good", "will check and come back", "thanks!", "on it", "noted", "sure, one sec",
          "lunch now, back in 20", "back", "cool", "any update?", "not yet", "got it", "👍"]


def _capture(client):
    """Inki's model swapped for one that keeps what it was shown and answers plainly."""
    seen = []

    class Model:
        async def run(self, task):
            if task.name != "inki.reply":  # rewording the question and the like: their offline answers
                return task.heuristic()
            seen.append(task)
            return SimpleNamespace(reply="Noted.")

    prism = client.app.state.prism
    real = prism.guarded_providers
    prism.guarded_providers = lambda redactor: (lambda out: (out[0], Model(), *out[2:]))(real(redactor))
    return seen


def _ask(client, token, cid, text, seen, before):
    assert _send(client, token, cid, text=text).status_code == 201
    deadline = time.monotonic() + 10
    while len(seen) == before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(seen) > before, "Inki was not asked"
    return seen[-1]


def test_a_decision_from_early_in_a_long_conversation_reaches_inki(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    assert client.post("/conversations/inki-consent", headers=_auth(world["reviewer"]),
                       json={"accept": True}).status_code == 200
    _send(client, world["reviewer"], cid, text="For the festive post use the blue logo variant, not the red one.")
    _send(client, world["creator"], cid, text="Understood, blue logo variant it is.")
    for i in range(30):
        _send(client, world["creator" if i % 2 else "reviewer"], cid, text=FILLER[i % len(FILLER)])
    seen = _capture(client)
    task = _ask(client, world["reviewer"], cid, "@Inki which logo variant did we agree for the festive post?", seen, 0)
    recent = " ".join(t for _, t in task.transcript)
    earlier = " ".join(t for _, t in task.earlier)
    assert "blue logo" not in recent  # long gone from the recent turns
    assert "blue logo variant, not the red" in earlier and "blue logo variant it is" in earlier  # and its reply
    assert len(task.earlier) <= 2 * client.app.state.settings.memory_recall_turns

    # The vectors made for it are sealed with the conversation's key, not readable numbers.
    async def rows():
        async with client.app.state.db.sessionmaker() as s:
            from sqlalchemy import select
            return (await s.scalars(select(MessageVector).where(MessageVector.conversation_id == cid))).all()
    stored = client.portal.call(rows)
    assert stored and all(r.sealed.startswith("v1.") for r in stored)
    seal = client.app.state.message_seal
    assert seal.open(cid, stored[0].sealed) is not None and seal.open(cid + 1, stored[0].sealed) is None


def test_recall_can_be_turned_off(client, world):  # noqa: F811
    client.app.state.settings.memory_enabled = False
    try:
        cid, _ = _start(client, world)
        client.post("/conversations/inki-consent", headers=_auth(world["reviewer"]), json={"accept": True})
        _send(client, world["reviewer"], cid, text="Use the blue logo variant.")
        for i in range(20):
            _send(client, world["creator"], cid, text=FILLER[i % len(FILLER)])
        seen = _capture(client)
        task = _ask(client, world["reviewer"], cid, "@Inki which logo variant?", seen, 0)
        assert task.earlier == []
    finally:
        client.app.state.settings.memory_enabled = True


# --- what a person tells Ask Inki ---------------------------------------------------------------------------

def _thread(client, token, *said, tid=None):
    msgs = [m for s in said for m in ({"role": "user", "content": s}, {"role": "assistant", "content": "Okay."})]
    if tid is None:
        res = client.post("/chats", headers=_auth(token), json={"title": "Chat", "messages": msgs})
    else:
        res = client.put(f"/chats/{tid}", headers=_auth(token), json={"title": "Chat", "messages": msgs})
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _memories(client, token, at_least=1):
    deadline = time.monotonic() + 10
    while True:
        got = client.get("/me/memories", headers=_auth(token)).json()
        if len(got) >= at_least or time.monotonic() > deadline:
            return got
        time.sleep(0.05)


def test_ask_inki_keeps_what_a_person_says_about_how_they_work(client, world):  # noqa: F811
    tid = _thread(client, world["creator"], "I run the Instagram channel for the brand. Can you check my last post?")
    kept = _memories(client, world["creator"])
    assert [m["text"] for m in kept] == ["I run the Instagram channel for the brand"]
    # Said again in other words later in the same thread: one fact, not two piled up.
    _thread(client, world["creator"], "I run the Instagram channel for the brand. Can you check my last post?",
            "Also, I prefer short bullet answers.", tid=tid)
    kept = _memories(client, world["creator"], 2)
    assert sorted(m["text"] for m in kept) == ["I prefer short bullet answers",
                                               "I run the Instagram channel for the brand"]
    # Read back into Ask Inki's context when the question is near it.
    ctx = client.get("/assistant/context", headers=_auth(world["creator"]),
                     params={"q": "which channel do I post on?"}).json()
    assert "I run the Instagram channel for the brand" in ctx["about_you"]


def test_questions_and_other_peoples_words_are_not_kept(client, world):  # noqa: F811
    _thread(client, world["creator"], "Can I post on Friday?", "What is still open on my piece?")
    time.sleep(0.3)
    assert client.get("/me/memories", headers=_auth(world["creator"])).json() == []


def test_one_persons_memory_never_reaches_another(client, world):  # noqa: F811
    _thread(client, world["creator"], "I handle the LinkedIn page and I always post on Mondays.")
    mine = _memories(client, world["creator"])
    assert mine
    assert client.get("/me/memories", headers=_auth(world["reviewer"])).json() == []
    ctx = client.get("/assistant/context", headers=_auth(world["reviewer"]), params={"q": "LinkedIn Mondays"}).json()
    assert ctx.get("about_you") == []
    # Nor can another person delete it by its id.
    assert client.delete(f"/me/memories/{mine[0]['id']}", headers=_auth(world["reviewer"])).status_code == 404
    assert len(client.get("/me/memories", headers=_auth(world["creator"])).json()) == len(mine)


def test_a_confidential_term_is_never_kept(client, world):  # noqa: F811
    _thread(client, world["creator"], "I work on the Project Lumen launch posts.", "I prefer short answers.")
    kept = _memories(client, world["creator"])
    assert kept and all("lumen" not in m["text"].lower() for m in kept)


def test_forgetting_one_or_everything(client, world):  # noqa: F811
    _thread(client, world["creator"], "I run the Instagram channel.", "I prefer short answers.")
    kept = _memories(client, world["creator"], 2)
    assert client.delete(f"/me/memories/{kept[0]['id']}", headers=_auth(world["creator"])).json() == {"forgotten": 1}
    assert len(client.get("/me/memories", headers=_auth(world["creator"])).json()) == len(kept) - 1
    assert client.delete("/me/memories", headers=_auth(world["creator"])).json()["forgotten"] == len(kept) - 1
    assert client.get("/me/memories", headers=_auth(world["creator"])).json() == []
    assert client.delete("/me/memories/not-a-real-id", headers=_auth(world["creator"])).status_code == 404


def test_a_fact_is_read_back_only_within_the_clearance_it_was_kept_at(client, world):  # noqa: F811
    from verytas.memory.personal import Scope

    personal = client.app.state.personal
    secret = Scope(1, 999, "confidential")

    async def go():
        await personal.remember(secret, ["Leads the board-exam campaign planning"])
        return (await personal.recall(secret, "campaign planning", ["public", "internal"], 5),
                await personal.recall(secret, "campaign planning", ["public", "internal", "confidential"], 5))

    lower, full = client.portal.call(go)
    assert lower == [] and full == ["Leads the board-exam campaign planning"]


def test_forgotten_facts_leave_nothing_on_disk(client, world):  # noqa: F811
    _thread(client, world["creator"], "I run the Zebra newsletter for the brand.")
    assert _memories(client, world["creator"])
    client.delete("/me/memories", headers=_auth(world["creator"]))
    store = client.app.state.personal.directory
    left = b"".join(p.read_bytes() for p in store.rglob("*") if p.is_file())
    assert b"Zebra" not in left  # no history log of what was said, deleted or not


def _on(token, device):
    return {**_auth(token), "X-Verytas-Device": device}


def test_a_shared_demo_person_keeps_facts_per_browser(client, world):  # noqa: F811
    one, two = "browserOne_0123456789abcd", "browserTwo_0123456789abcd"
    msgs = [{"role": "user", "content": "I'm a designer and I prefer short answers."},
            {"role": "assistant", "content": "Okay."}]
    assert client.post("/chats", headers=_on(world["creator"], one), json={"title": "Chat", "messages": msgs}).status_code == 201
    deadline = time.monotonic() + 10
    while not (kept := client.get("/me/memories", headers=_on(world["creator"], one)).json()) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert kept
    # Another visitor who picked the same person, on another browser, starts with nothing and can't delete it.
    assert client.get("/me/memories", headers=_on(world["creator"], two)).json() == []
    ctx = client.get("/assistant/context", headers=_on(world["creator"], two), params={"q": "designer short answers"}).json()
    assert ctx.get("about_you") == []
    assert client.delete(f"/me/memories/{kept[0]['id']}", headers=_on(world["creator"], two)).status_code == 404
    # Nor does it reach the person's own (non-shared) sessions, or a shared one whose browser id is missing.
    assert client.get("/me/memories", headers=_auth(world["creator"])).json() == []
    assert client.get("/me/memories", headers=_on(world["creator"], "-")).json() == []
    ctx = client.get("/assistant/context", headers=_on(world["creator"], one), params={"q": "designer short answers"}).json()
    assert ctx.get("about_you")


def test_a_shared_demo_persons_saved_chats_stay_with_their_browser(client, world):  # noqa: F811
    one, two = "chatsOne_0123456789abcdef", "chatsTwo_0123456789abcdef"
    msgs = [{"role": "user", "content": "Draft me three hooks for the festive reel."}, {"role": "assistant", "content": "Okay."}]
    tid = client.post("/chats", headers=_on(world["creator"], one), json={"title": "Hooks", "messages": msgs}).json()["id"]
    assert [t["id"] for t in client.get("/chats", headers=_on(world["creator"], one)).json()] == [tid]
    # The next visitor on the same person, and the person's own sign-in, neither list nor open nor change it.
    assert client.get("/chats", headers=_on(world["creator"], two)).json() == []
    assert client.get("/chats", headers=_auth(world["creator"])).json() == []
    assert client.get(f"/chats/{tid}", headers=_on(world["creator"], two)).status_code == 404
    assert client.put(f"/chats/{tid}", headers=_on(world["creator"], two), json={"title": "x", "messages": msgs}).status_code == 404
    assert client.delete(f"/chats/{tid}", headers=_auth(world["creator"])).status_code == 404
    # A shared sign-in without a usable browser id reads nothing and can't save.
    assert client.get("/chats", headers=_on(world["creator"], "-")).json() == []
    assert client.post("/chats", headers=_on(world["creator"], "-"), json={"title": "x", "messages": msgs}).status_code == 409
    assert client.delete(f"/chats/{tid}", headers=_on(world["creator"], one)).status_code == 204


def test_a_shared_sign_ins_facts_lapse_after_a_day(client, world):  # noqa: F811
    from datetime import UTC, datetime, timedelta

    from verytas.memory.personal import Scope

    personal = client.app.state.personal
    shared, own = Scope(1, 998, "public", device="lapseTest_0123456789abc"), Scope(1, 998, "public")

    async def go():
        await personal.remember(shared, ["Writes the weekly study-tips reel"])
        await personal.remember(own, ["Signs off the LinkedIn copy"])
        early = await personal.sweep(datetime.now(UTC) + timedelta(hours=23))
        late = await personal.sweep(datetime.now(UTC) + timedelta(hours=25))
        return early, late, await personal.listing(shared), await personal.listing(own)

    early, late, left_shared, left_own = client.portal.call(go)
    assert (early, late) == (0, 1) and left_shared == []
    assert [r["text"] for r in left_own] == ["Signs off the LinkedIn copy"]  # a person's own facts never lapse


def test_a_deleted_message_takes_its_vector_with_it(client, world):  # noqa: F811
    cid, _ = _start(client, world)
    client.post("/conversations/inki-consent", headers=_auth(world["reviewer"]), json={"accept": True})
    first = _send(client, world["reviewer"], cid, text="The launch budget is fifteen thousand all in.").json()["id"]
    for i in range(30):
        _send(client, world["creator" if i % 2 else "reviewer"], cid, text=f"{FILLER[i % len(FILLER)]} about item {i}")
    seen = _capture(client)
    _ask(client, world["reviewer"], cid, "@Inki what is the launch budget?", seen, 0)

    async def vector_ids():
        async with client.app.state.db.sessionmaker() as s:
            from sqlalchemy import select
            return set((await s.scalars(select(MessageVector.message_id).where(
                MessageVector.conversation_id == cid))).all())
    assert first in client.portal.call(vector_ids)
    assert client.delete(f"/conversations/{cid}/messages/{first}", headers=_auth(world["reviewer"])).status_code == 200
    assert first not in client.portal.call(vector_ids)


def test_two_questions_embedding_the_same_turns_both_succeed(client, world):  # noqa: F811
    import asyncio

    from verytas.memory.thread import Turn, VectorCache

    cid, _ = _start(client, world)
    ids = [_send(client, world["creator"], cid, text=f"turn number {i} about the reel").json()["id"] for i in range(12)]
    turns = [Turn(i, "Creator", f"turn number {n} about the reel") for n, i in enumerate(ids)]
    cache = VectorCache(client.app.state.db, client.app.state.message_seal)

    async def both():
        return await asyncio.gather(*(cache.vectors(client.app.state.embedder, cid, turns) for _ in range(2)))

    a, b = client.portal.call(both)
    assert a.shape == b.shape == (12, client.app.state.embedder.dims)


def test_a_lone_decision_among_acknowledgements_still_comes(client, world):  # noqa: F811
    from verytas.memory.embed import HashEmbedder
    from verytas.memory.thread import NoCache, Turn, earlier_turns

    older = [Turn(1, "Brand team", "Use the blue logo variant for the festive post.")]
    older += [Turn(i, "Creator", FILLER[i % len(FILLER)].split()[0]) for i in range(2, 20)]

    async def go():
        return await earlier_turns(NoCache(), HashEmbedder(), 1, older, "@Inki which logo?", 6)

    picked = client.portal.call(go)
    assert picked[0].message_id == 1 and len(picked) == 2  # the decision and the reply after it


def test_a_failed_fact_call_leaves_the_messages_for_the_next_save(client, world):  # noqa: F811
    prism = client.app.state.prism
    real = prism.guarded_providers

    class Down:
        async def run(self, task):
            raise RuntimeError("provider down")

    prism.guarded_providers = lambda redactor: (lambda out: (out[0], Down(), *out[2:]))(real(redactor))
    tid = _thread(client, world["creator"], "I run the Instagram channel for the brand.")
    time.sleep(0.3)
    assert client.get("/me/memories", headers=_auth(world["creator"])).json() == []
    prism.guarded_providers = real
    # The next save reads the same message again, now that the model answers.
    _thread(client, world["creator"], "I run the Instagram channel for the brand.", "Thanks.", tid=tid)
    assert [m["text"] for m in _memories(client, world["creator"])] == ["I run the Instagram channel for the brand"]


def test_learning_stops_at_the_hourly_limit(client, world):  # noqa: F811
    from verytas.services.inki_guard import RateLimit

    client.app.state.learning = RateLimit(per_hour=0)
    _thread(client, world["creator"], "I run the Instagram channel for the brand.")
    time.sleep(0.3)
    assert client.get("/me/memories", headers=_auth(world["creator"])).json() == []


def test_the_question_is_reworded_only_when_there_is_a_history_to_rank():
    from verytas.memory.thread import Turn, ranks

    chatter = [Turn(i, "Creator", "ok") for i in range(30)]
    decisions = [Turn(100 + i, "Brand team", f"Decision number {i} about the reel cover") for i in range(4)]
    assert not ranks(chatter[:4] + decisions)   # short: all of it comes, unranked
    assert not ranks(chatter + decisions[:3])   # long, but too few real turns to rank
    assert ranks(chatter + decisions)
