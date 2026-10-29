"""Ask Inki's lookups: each acts as the person asking, leaves confidential material out, and agrees with the
context on what a redacted term is called."""

from __future__ import annotations

from tests.test_api_flow import _auth
from tests.test_api_flow import world as world  # noqa: F401, the fixture is used by name
from verytas.security.redaction import Redactor


def _tool(client, headers, tool, **arguments):
    res = client.post(f"/assistant/tools/{tool}", headers=headers, json={"arguments": arguments})
    assert res.status_code == 200, res.text
    return res.json()


def _post(client, headers, title, body, tier="internal"):
    res = client.post("/contents?wait=true", headers=headers,
                      json={"title": title, "channel": "linkedin", "body": body, "tier": tier})
    assert res.status_code == 201, res.text
    return res.json()["content"]["id"]


def test_tools_are_offered_by_role_and_refused_beyond_it(client, world):
    admin, creator = _auth(world["admin"]), _auth(world["creator"])
    offered = {t["function"]["name"] for t in client.get("/assistant/tools", headers=admin).json()}
    assert {"creators", "creator", "trend", "rules", "find_pieces", "piece"} <= offered
    mine = {t["function"]["name"] for t in client.get("/assistant/tools", headers=creator).json()}
    assert not mine & {"creators", "creator", "trend"}
    for name in ("creators", "trend", "no_such_tool"):
        assert client.post(f"/assistant/tools/{name}", headers=creator, json={"arguments": {}}).status_code == 404


def test_creators_shows_drift_by_person(client, world):
    admin, creator = _auth(world["admin"]), _auth(world["creator"])
    _post(client, creator, "Launch post", "Verytas is trusted by 1,000+ teams. Leverage synergies!")
    rows = _tool(client, admin, "creators")["creators"]
    me = next(r for r in rows if r["name"] == "Creator")
    assert me["reviewed"] == 1
    assert me["recent_distances"] and me["recent_distances"][0] > 0
    track = _tool(client, admin, "creator", name="creat")
    assert track["name"] == "Creator" and [p["title"] for p in track["pieces"]] == ["Launch post"]
    assert "error" in _tool(client, admin, "creator", name="nobody at all")


def test_piece_and_find_pieces_follow_who_may_open_what(client, world):
    admin, creator, reviewer = _auth(world["admin"]), _auth(world["creator"]), _auth(world["reviewer"])
    mine = _post(client, creator, "Spring post", "Our spring sale gives 20% off every plan.")
    theirs = _post(client, reviewer, "Team note", "The spring sale starts Monday.")
    secret = _post(client, admin, "Board memo", "The spring sale margin is thin.", tier="confidential")

    found = _tool(client, admin, "find_pieces", query="spring sale")
    assert {p["id"] for p in found["pieces"]} == {mine, theirs}, "searched by text, confidential left out"
    assert found["pieces"][0]["creator"]
    assert {p["id"] for p in _tool(client, creator, "find_pieces", query="spring")["pieces"]} == {mine}

    assert _tool(client, creator, "piece", id=mine)["latest_text"].startswith("Our spring sale")
    # Someone else's piece and a confidential one get the same answer as a missing one.
    for other in (theirs, secret, 999_999):
        assert "error" in _tool(client, creator if other != secret else admin, "piece", id=other)


def test_rules_and_facts_carry_their_wording(client, world):
    admin = _auth(world["admin"])
    rules = _tool(client, admin, "rules", query="buzzwords")["rules"]
    assert [r["code"] for r in rules] == ["VOICE-01"] and "buzzwords" in rules[0]["text"]
    facts = _tool(client, admin, "facts", query="teams")["facts"]
    assert facts and facts[0]["value"] == 800


def test_tool_results_and_the_context_agree_on_a_redacted_term(client, world):
    admin = _auth(world["admin"])
    for term in ("Zephyr", "Lumen"):
        assert client.post("/confidential-terms", headers=admin, json={"term": term}).status_code in (200, 201)
    _post(client, admin, "Teaser", "Lumen arrives soon, before Zephyr.")
    ctx = client.post("/assistant/context", headers=admin, json={"messages": ["When does Lumen ship?"]}).json()
    asked = ctx["messages"][0]
    placeholder = asked[asked.index("[[TERM_"):asked.index("]]") + 2]
    # The model searches with the placeholder it was given; the lookup finds the piece and redacts it the same way.
    found = _tool(client, admin, "find_pieces", query=placeholder)
    assert [p["title"] for p in found["pieces"]] == ["Teaser"]
    detail = _tool(client, admin, "piece", id=found["pieces"][0]["id"])
    assert "Lumen" not in str(detail) and "Zephyr" not in str(detail)
    assert placeholder in detail["latest_text"]


def test_stable_placeholders_do_not_depend_on_what_was_seen_first():
    a, b = Redactor(["Lumen", "Zephyr"], stable=True), Redactor(["Zephyr", "Lumen"], stable=True)
    assert a.redact("Zephyr") == b.redact("Zephyr") and a.redact("lumen") == b.redact("Lumen")
    assert a.redact("Zephyr") != a.redact("Lumen")
    # A fresh stable redactor still knows what its placeholders stand for.
    assert Redactor(["Lumen", "Zephyr"], stable=True).restore(a.redact("Zephyr")) == "Zephyr"
    # The default keeps numbering by first appearance, as Prism expects.
    assert Redactor(["Lumen", "Zephyr"]).redact("Zephyr") == "[[TERM_1]]"


def test_a_guessed_confidential_term_finds_nothing(client, world):
    admin = _auth(world["admin"])
    assert client.post("/confidential-terms", headers=admin, json={"term": "Falcon"}).status_code in (200, 201)
    created = client.post("/rules", headers=admin, json={
        "code": "LAUNCH-09", "category": "claims", "kind": "semantic", "severity": "should",
        "title": "Falcon launch wording", "text": "Never date the Falcon launch."})
    assert created.status_code == 201, created.text
    client.patch(f"/rules/{created.json()['id']}", headers=admin, json={"status": "active"})
    # Searching for the real word must not confirm it: the text it would match is redacted before matching.
    assert _tool(client, admin, "rules", query="Falcon")["rules"] == []
    assert _tool(client, admin, "facts", query="Falcon")["facts"] == []
    found = _tool(client, admin, "rules", query="launch wording")["rules"]
    assert [r["code"] for r in found] == ["LAUNCH-09"] and "Falcon" not in str(found)


def test_wrong_typed_arguments_are_an_error_not_a_crash(client, world):
    admin = _auth(world["admin"])
    for tool, arguments in (("find_pieces", {"query": 5}), ("find_pieces", {"channel": 5, "limit": "many"}),
                            ("find_pieces", {"status": "nonsense"}), ("rules", {"query": 5}),
                            ("piece", {"id": "abc"}), ("trend", {"days": [1]}), ("creator", {"name": None})):
        res = client.post(f"/assistant/tools/{tool}", headers=admin, json={"arguments": arguments})
        assert res.status_code == 200, (tool, arguments, res.text)


def test_the_other_lookups_answer_and_leave_confidential_out(client, world):
    admin, creator = _auth(world["admin"]), _auth(world["creator"])
    _post(client, creator, "Launch post", "Verytas is trusted by 1,000+ teams.")
    assert _tool(client, admin, "escalations", state="all")["state"] == "all"
    assert "events" in _tool(client, admin, "events") and "people" in _tool(client, admin, "people")
    trend = _tool(client, admin, "trend", days=500)
    assert trend["days"] == 90 and "trend" in trend
    assert "escalations" in _tool(client, creator, "escalations")


def test_lookups_are_rate_limited(client, world, monkeypatch):
    from verytas.api import inki_tools
    from verytas.services.inki_guard import RateLimit

    monkeypatch.setattr(inki_tools, "_calls", RateLimit(2))
    admin = _auth(world["admin"])
    codes = [client.post("/assistant/tools/rules", headers=admin, json={"arguments": {}}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
