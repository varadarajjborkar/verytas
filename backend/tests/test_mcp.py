"""The /mcp endpoint and the personal tokens behind it (docs/mcp.md).

What matters here is what a token can never do: act as anyone else, see what its person could not, reach
the REST API, or outlive its revocation. Everything runs offline over the real ASGI app.
"""

from __future__ import annotations

import json
import re
import time

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_api_flow import _auth, world  # noqa: F401, the fixture is used by name
from verytas.config import Settings
from verytas.main import create_app
from verytas.models import AuditEntry, PersonalToken, Role, User, Workspace, utcnow

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
SPY = "Project Lumen"


def _make_token(client, session_token, *, scopes=("read",), days=None, name="laptop"):
    body = {"name": name, "scopes": list(scopes)}
    if days is not None:
        body["days"] = days
    r = client.post("/me/tokens", headers=_auth(session_token), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _rpc(client, pat, method, params=None, *, origin=None, rid=1):
    headers = {**HEADERS, "Authorization": f"Bearer {pat}"}
    if origin:
        headers["Origin"] = origin
    return client.post("/mcp", headers=headers,
                       json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})


def _call(client, pat, tool, **arguments):
    """Returns (is_error, result): the decoded JSON of a good call, the message of a refused one."""
    r = _rpc(client, pat, "tools/call", {"name": tool, "arguments": arguments})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    text = result["content"][0]["text"]
    return result["isError"], (text if result["isError"] else json.loads(text))


def _creator(client, world, name):  # noqa: F811
    r = client.post("/users", headers=_auth(world["admin"]),
                    json={"email": f"{name}@acme.io", "name": name.title(), "role": "creator"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def _submit(client, token, title="Note", body="A plain note about the week.", **extra):
    r = client.post("/contents?wait=true", headers=_auth(token), json={"title": title, "body": body, **extra})
    assert r.status_code == 201, r.text
    return r.json()["content"]["id"]


# --- tokens ---------------------------------------------------------------------------------------------

def test_token_lifecycle(client, world):  # noqa: F811
    made = _make_token(client, world["creator"], scopes=("write",))
    secret = made["token"]
    assert secret.startswith("vt_pat_") and len(secret) > 40
    assert made["scopes"] == ["read", "write"], "read is always included"
    assert made["prefix"] == secret[len("vt_pat_"):][:8]
    assert made["revoked_at"] is None and made["last_used_at"] is None

    listed = client.get("/me/tokens", headers=_auth(world["creator"]))
    assert listed.status_code == 200 and secret not in listed.text
    assert "token" not in listed.json()[0] and "token_hash" not in listed.json()[0]

    isError, who = _call(client, secret, "whoami")
    assert not isError and who["name"] == "Creator"
    assert client.get("/me/tokens", headers=_auth(world["creator"])).json()[0]["last_used_at"] is not None

    assert client.delete(f"/me/tokens/{made['id']}", headers=_auth(world["creator"])).status_code == 204
    revoked = client.get("/me/tokens", headers=_auth(world["creator"])).json()[0]
    assert revoked["revoked_at"] is not None
    assert _rpc(client, secret, "tools/list").status_code == 401


def test_expiry_defaults_and_is_capped(client, world):  # noqa: F811
    made = _make_token(client, world["creator"])
    days = (time.mktime(time.strptime(made["expires_at"][:19], "%Y-%m-%dT%H:%M:%S"))
            - time.mktime(time.strptime(made["created_at"][:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
    assert round(days) == 30
    for bad in (0, 91, 365):
        r = client.post("/me/tokens", headers=_auth(world["creator"]), json={"name": "x", "days": bad})
        assert r.status_code == 422
    assert client.post("/me/tokens", headers=_auth(world["creator"]), json={"name": "x" * 61}).status_code == 422
    assert client.post("/me/tokens", headers=_auth(world["creator"]),
                       json={"name": "x", "scopes": ["admin"]}).status_code == 422


def test_five_active_tokens_at_most(client, world):  # noqa: F811
    made = [_make_token(client, world["creator"], name=f"t{i}") for i in range(5)]
    assert client.post("/me/tokens", headers=_auth(world["creator"]), json={"name": "sixth"}).status_code == 409
    client.delete(f"/me/tokens/{made[0]['id']}", headers=_auth(world["creator"]))
    assert client.post("/me/tokens", headers=_auth(world["creator"]), json={"name": "sixth"}).status_code == 201


def test_nobody_revokes_or_sees_another_persons_token(client, world):  # noqa: F811
    mine = _make_token(client, world["creator"])
    assert client.delete(f"/me/tokens/{mine['id']}", headers=_auth(world["reviewer"])).status_code == 404
    assert client.get("/me/tokens", headers=_auth(world["reviewer"])).json() == []
    assert not _call(client, mine["token"], "whoami")[0], "still valid after the failed revoke"


def test_token_changes_are_audited_without_the_secret(client, world):  # noqa: F811
    made = _make_token(client, world["creator"], name="desk")
    client.delete(f"/me/tokens/{made['id']}", headers=_auth(world["creator"]))
    log = client.get("/audit?object_type=token", headers=_auth(world["admin"]))
    assert log.status_code == 200
    actions = [e["action"] for e in log.json()]
    assert "token.created" in actions and "token.revoked" in actions
    assert made["token"] not in log.text and made["prefix"] not in log.text
    assert client.get("/audit/verify", headers=_auth(world["admin"])).json()["ok"]


# --- audiences ------------------------------------------------------------------------------------------

def test_a_personal_token_is_refused_by_every_rest_route(client, world):  # noqa: F811
    pat = _make_token(client, world["admin"], scopes=("read", "write"))["token"]
    for method, path in (("get", "/me"), ("get", "/contents"), ("get", "/rules"), ("get", "/audit"),
                         ("get", "/me/tokens"), ("post", "/me/tokens"), ("post", "/contents"), ("get", "/search")):
        r = getattr(client, method)(path, headers=_auth(pat))
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"
    assert client.post("/me/tokens", headers=_auth(pat), json={"name": "mint"}).status_code == 401


def test_a_session_token_is_refused_by_mcp(client, world):  # noqa: F811
    for secret in (world["admin"], world["creator"], "vt_" + "a" * 43, ""):
        r = _rpc(client, secret, "tools/list")
        assert r.status_code == 401
        assert r.headers["www-authenticate"].startswith("Bearer")
    bare = client.post("/mcp", headers=HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert bare.status_code == 401 and bare.headers["www-authenticate"] == 'Bearer realm="verytas-mcp"'


async def test_expired_and_revoked_tokens_are_refused(client, world):  # noqa: F811
    expired = _make_token(client, world["creator"], name="old")
    live = _make_token(client, world["creator"], name="new")
    async with client.app.state.db.sessionmaker() as s:
        row = await s.get(PersonalToken, expired["id"])
        row.expires_at = utcnow().replace(year=2020)
        await s.commit()
    assert _rpc(client, expired["token"], "tools/list").status_code == 401
    assert _rpc(client, live["token"], "tools/list").status_code == 200
    # Past the day: the person is still the same, the token is simply spent.
    assert [t["name"] for t in client.get("/me/tokens", headers=_auth(world["creator"])).json()] == ["new", "old"]


async def test_a_token_dies_with_the_workspace_membership(client, world):  # noqa: F811
    made = _make_token(client, world["creator"])
    async with client.app.state.db.sessionmaker() as s:
        elsewhere = Workspace(name="Elsewhere")
        s.add(elsewhere)
        await s.flush()
        (await s.get(PersonalToken, made["id"])).workspace_id = elsewhere.id
        await s.commit()
    assert _rpc(client, made["token"], "tools/list").status_code == 401


async def test_last_used_is_written_at_most_once_a_minute(client, world):  # noqa: F811
    made = _make_token(client, world["creator"])
    _call(client, made["token"], "whoami")
    async with client.app.state.db.sessionmaker() as s:
        first = (await s.get(PersonalToken, made["id"])).last_used_at
    _call(client, made["token"], "whoami")
    async with client.app.state.db.sessionmaker() as s:
        assert (await s.get(PersonalToken, made["id"])).last_used_at == first


# --- origin ---------------------------------------------------------------------------------------------

def test_a_browser_origin_is_refused_unless_listed(client, world, settings):  # noqa: F811
    pat = _make_token(client, world["creator"])["token"]
    assert _rpc(client, pat, "tools/list").status_code == 200, "no Origin header: not a browser"
    assert _rpc(client, pat, "tools/list", origin="http://evil.example").status_code == 403
    assert _rpc(client, pat, "tools/list", origin="null").status_code == 403
    # Refused before the token is looked at, so a page learns nothing about which tokens exist.
    assert _rpc(client, "vt_pat_nonsense", "tools/list", origin="http://evil.example").status_code == 403


def test_a_listed_origin_passes(tmp_path):
    cfg = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'o.db'}", llm_mode="offline",
                   keys_dir=tmp_path / "keys", faces_enabled=False, mcp_allowed_origins=["https://app.example"])
    with TestClient(create_app(cfg)) as c:
        boot = c.post("/bootstrap", json={"workspace_name": "A", "admin_email": "a@a.io", "admin_name": "A"})
        pat = _make_token(c, boot.json()["token"])["token"]
        assert _rpc(c, pat, "tools/list", origin="https://app.example/").status_code == 200
        assert _rpc(c, pat, "tools/list", origin="https://other.example").status_code == 403


# --- scopes, rate limit ---------------------------------------------------------------------------------

def test_a_read_only_token_cannot_use_a_write_tool(client, world):  # noqa: F811
    pat = _make_token(client, world["creator"], scopes=("read",))["token"]
    is_error, msg = _call(client, pat, "submit_content", title="T", text="Hello there.")
    assert is_error and "no 'write' access" in msg
    is_error, msg = _call(client, pat, "add_comment", content_id=1, text="hi")
    assert is_error and "no 'write' access" in msg
    assert client.get("/contents", headers=_auth(world["creator"])).json() == []
    ok, _ = _call(client, pat, "list_content")
    assert not ok


def test_tool_calls_are_rate_limited_per_token(tmp_path):
    cfg = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'r.db'}", llm_mode="offline",
                   keys_dir=tmp_path / "keys", faces_enabled=False, mcp_calls_per_minute=3)
    with TestClient(create_app(cfg)) as c:
        admin = c.post("/bootstrap", json={"workspace_name": "A", "admin_email": "a@a.io",
                                           "admin_name": "A"}).json()["token"]
        one, two = _make_token(c, admin, name="one")["token"], _make_token(c, admin, name="two")["token"]
        for _ in range(3):
            assert not _call(c, one, "whoami")[0]
        is_error, msg = _call(c, one, "whoami")
        assert is_error and "rate limit" in msg
        assert not _call(c, two, "whoami")[0], "the limit is per token"
        # Listing tools is not a tool call.
        assert _rpc(c, one, "tools/list").status_code == 200
        actions = [e["detail"] for e in c.get("/audit?object_type=token", headers=_auth(admin)).json()
                   if e["action"] == "mcp.tool"]
        assert [a for a in actions if a.get("reason") == "rate_limited"], "the first refusal is on record"


# --- acting as the person ---------------------------------------------------------------------------------

def test_a_creator_cannot_read_another_creators_piece(client, world):  # noqa: F811
    other = _creator(client, world, "other")
    theirs = _submit(client, other, "Their draft", "Secret plans for next week.")
    mine = _submit(client, world["creator"], "My draft")
    pat = _make_token(client, world["creator"])["token"]

    is_error, msg = _call(client, pat, "get_review", content_id=theirs)
    assert is_error and "not found" in msg and "Secret plans" not in msg
    ok, listing = _call(client, pat, "list_content")
    assert not ok and [i["id"] for i in listing["items"]] == [mine]
    _, hits = _call(client, pat, "search", query="Their draft")
    assert all(h["id"] != theirs for h in hits["hits"] if h["kind"] == "content")
    is_error, _ = _call(client, _make_token(client, world["creator"], scopes=("write",))["token"], "add_comment",
                        content_id=theirs, text="Hello")
    assert is_error, "comments go through the same visibility check"
    # A brand reviewer, who may see it in the app, may through a token too.
    rv = _make_token(client, world["reviewer"])["token"]
    ok, review = _call(client, rv, "get_review", content_id=theirs)
    assert not ok and review["version"]["text"].startswith("Secret plans")


def test_confidential_terms_never_leave(client, world):  # noqa: F811
    cid = _submit(client, world["creator"], "Launch", f"{SPY} brings video review next month!")
    for who, scopes in (("creator", ("read",)), ("admin", ("read", "write")), ("reviewer", ("read",))):
        pat = _make_token(client, world[who], scopes=scopes)["token"]
        seen = [r.text for r in (
            _rpc(client, pat, "tools/call", {"name": "get_review", "arguments": {"content_id": cid}}),
            _rpc(client, pat, "tools/call", {"name": "list_content", "arguments": {}}),
            _rpc(client, pat, "tools/call", {"name": "list_rules", "arguments": {}}),
            _rpc(client, pat, "tools/call", {"name": "search", "arguments": {"query": "Lumen"}}),
            _rpc(client, pat, "tools/call", {"name": "search", "arguments": {"query": "Launch"}}),
            _rpc(client, pat, "tools/call", {"name": "precheck_text", "arguments": {"text": f"About {SPY}"}}),
        )]
        assert not any("lumen" in t.lower() for t in seen), who
    ok, review = _call(client, _make_token(client, world["creator"])["token"], "get_review", content_id=cid)
    assert "[[TERM_1]]" in review["version"]["text"]
    assert any(f["rule"] and f["rule"].startswith("CONF-LEAK") for f in review["review"]["findings"])
    _, hits = _call(client, _make_token(client, world["admin"])["token"], "search", query="Lumen")
    assert all(h["kind"] in ("content", "finding", "rule") for h in hits["hits"])


def test_confidential_tier_stays_out_by_default(client, world):  # noqa: F811
    cid = _submit(client, world["admin"], "Board memo", "Numbers for the board.", tier="confidential")
    assert any(i["id"] == cid for i in client.get("/contents", headers=_auth(world["admin"])).json())
    pat = _make_token(client, world["admin"], scopes=("read", "write"))["token"]
    _, who = _call(client, pat, "whoami")
    assert who["clearance"] == "internal"
    _, listing = _call(client, pat, "list_content")
    assert all(i["id"] != cid for i in listing["items"])
    assert _call(client, pat, "get_review", content_id=cid)[0]
    assert _call(client, pat, "add_comment", content_id=cid, text="hello")[0]
    assert _call(client, pat, "submit_content", title="T", text="x", tier="confidential")[0], "not in the schema"


def test_submit_review_and_comment_round_trip(client, world):  # noqa: F811
    pat = _make_token(client, world["creator"], scopes=("read", "write"))["token"]
    is_error, made = _call(client, pat, "submit_content", title="Newsletter", channel="email",
                           text="Please sign-in to leverage synergies.", ai_used=True)
    assert not is_error and made["content_id"] and made["review_id"]
    review = None
    for _ in range(100):
        _, got = _call(client, pat, "get_review", content_id=made["content_id"])
        if got["review"] and got["review"]["status"] in ("done", "failed"):
            review = got["review"]
            break
        time.sleep(0.1)
    assert review and review["status"] == "done" and review["findings"]
    one = review["findings"][0]
    assert {"level", "title", "explanation", "quote"} <= set(one)
    # The same piece, through the REST API, was created by the same person.
    rest = client.get(f"/contents/{made['content_id']}", headers=_auth(world["creator"])).json()
    assert rest["title"] == "Newsletter" and rest["status"] == "draft"

    ok, comment = _call(client, pat, "add_comment", content_id=made["content_id"], text="Remember the launch date.")
    assert not ok
    comments = client.get(f"/contents/{made['content_id']}/comments", headers=_auth(world["creator"])).json()
    assert [c["body"] for c in comments] == ["Remember the launch date."]
    assert comments[0]["id"] == comment["comment_id"] and comments[0]["actor_id"] is not None


def test_no_tool_can_decide_approve_or_administer(client, world):  # noqa: F811
    pat = _make_token(client, world["admin"], scopes=("read", "write"))["token"]
    names = {t["name"] for t in _rpc(client, pat, "tools/list").json()["result"]["tools"]}
    assert names == {"whoami", "list_content", "get_review", "list_rules", "search", "precheck_text",
                     "submit_content", "add_comment"}
    assert not any(re.search(r"decide|approve|publish|term|token|admin|user|rule_", n) for n in names
                   if n != "list_rules")
    assert _rpc(client, pat, "tools/call", {"name": "approve", "arguments": {}}).json()["result"]["isError"]


def test_tools_are_annotated_and_bounded(client, world):  # noqa: F811
    pat = _make_token(client, world["creator"])["token"]
    tools = {t["name"]: t for t in _rpc(client, pat, "tools/list").json()["result"]["tools"]}
    for name in ("whoami", "list_content", "get_review", "list_rules", "search", "precheck_text"):
        assert tools[name]["annotations"]["readOnlyHint"] is True, name
    for name in ("submit_content", "add_comment"):
        hints = tools[name]["annotations"]
        assert hints["readOnlyHint"] is False and hints["destructiveHint"] is False
    props = tools["submit_content"]["inputSchema"]["properties"]
    assert props["text"]["maxLength"] == 100_000 and props["title"]["maxLength"] == 300
    assert tools["list_content"]["inputSchema"]["properties"]["limit"]["maximum"] == 50
    assert tools["search"]["inputSchema"]["properties"]["query"]["maxLength"] == 100
    assert _call(client, pat, "list_content", limit=51)[0]
    assert _call(client, pat, "search", query="x" * 101)[0]


def test_every_tool_call_is_audited_without_its_arguments(client, world):  # noqa: F811
    pat = _make_token(client, world["creator"], scopes=("read", "write"))["token"]
    _call(client, pat, "precheck_text", text="Unmistakable draft wording.")
    _call(client, pat, "submit_content", title="Unmistakable title", text="Unmistakable body.")
    ro = _make_token(client, world["creator"], name="ro")["token"]
    _call(client, ro, "add_comment", content_id=1, text="Unmistakable comment")
    log = client.get("/audit?object_type=token", headers=_auth(world["admin"]))
    calls = [e for e in log.json() if e["action"] == "mcp.tool"]
    assert {(e["detail"]["tool"], e["detail"]["ok"]) for e in calls} >= {
        ("precheck_text", True), ("submit_content", True), ("add_comment", False)}
    assert "Unmistakable" not in log.text
    assert client.get("/audit/verify", headers=_auth(world["admin"])).json()["ok"]


async def test_a_changed_role_applies_to_the_next_call(client, world):  # noqa: F811
    pat = _make_token(client, world["reviewer"], scopes=("read", "write"))["token"]
    assert not _call(client, pat, "submit_content", title="T", text="Hello there.")[0]
    async with client.app.state.db.sessionmaker() as s:
        (await s.scalar(select(User).where(User.email == "reviewer@acme.io"))).role = Role.auditor
        await s.commit()
    is_error, msg = _call(client, pat, "submit_content", title="T2", text="Hello again.")
    assert is_error and "needs role" in msg


def test_an_internal_failure_does_not_leak_detail(client, world, monkeypatch):  # noqa: F811
    from verytas.api import content as content_api

    async def boom(*a, **k):
        raise RuntimeError("db password is hunter2")

    monkeypatch.setattr(content_api, "list_contents", boom)
    pat = _make_token(client, world["creator"])["token"]
    is_error, msg = _call(client, pat, "list_content")
    assert is_error and "hunter2" not in msg


# --- the real protocol ------------------------------------------------------------------------------------

async def test_a_real_mcp_client_round_trip(tmp_path):
    """The SDK's own client against the app over ASGI: initialize, tools/list, tools/call."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    cfg = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'c.db'}", llm_mode="offline",
                   keys_dir=tmp_path / "keys", faces_enabled=False)
    app = create_app(cfg)

    def factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://verytas.test",
                                 headers=headers, timeout=timeout, auth=auth)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://verytas.test") as http:
            boot = await http.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                                        "admin_name": "Ada"})
            admin = boot.json()["token"]
            made = await http.post("/me/tokens", headers=_auth(admin), json={"name": "sdk", "scopes": ["read"]})
            pat = made.json()["token"]

        url = "http://verytas.test/mcp"
        headers = {"Authorization": f"Bearer {pat}"}
        async with (streamablehttp_client(url, headers=headers, httpx_client_factory=factory) as (read, write, _),
                    ClientSession(read, write) as session):
            init = await session.initialize()
            assert init.serverInfo.name == "Verytas" and "cannot decide" in init.instructions
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} >= {"whoami", "get_review", "submit_content"}
            who = await session.call_tool("whoami", {})
            assert not who.isError and who.structuredContent["name"] == "Ada"
            refused = await session.call_tool("submit_content", {"title": "T", "text": "Hello."})
            assert refused.isError


async def test_the_database_never_holds_a_token_in_the_clear(client, world):  # noqa: F811
    made = _make_token(client, world["creator"])
    async with client.app.state.db.sessionmaker() as s:
        hashes = (await s.scalars(select(PersonalToken.token_hash))).all()
        details = [json.dumps(e.detail) for e in (await s.scalars(select(AuditEntry))).all()]
    assert hashes and all(made["token"] not in h and len(h) == 64 for h in hashes)
    assert not any(made["token"] in d for d in details)


