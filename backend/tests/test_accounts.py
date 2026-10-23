"""Self-service accounts: off unless enabled, a company with its join code, creators joining it, password
sign-in, and the limits that keep a public demo from paying for strangers' model calls."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from verytas.config import Settings
from verytas.main import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def open_client(tmp_path):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'acc.db'}", llm_mode="offline",
                        keys_dir=tmp_path / "keys", faces_enabled=False, self_signup=True,
                        self_signup_max_workspaces=3, self_signup_per_hour=20, self_serve_actions_per_day=3)
    with TestClient(create_app(settings)) as c:
        yield c


def _company(c, email="mira@leafco.example", name="Leafco"):
    return c.post("/accounts/signup", json={"kind": "company", "company_name": name, "name": "Mira",
                                            "email": email, "password": PASSWORD})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_sign_up_is_off_unless_enabled(client):
    assert client.get("/accounts/config").json() == {"self_signup": False}
    assert _company(client).status_code == 404
    assert client.post("/accounts/signin", json={"email": "a@b.example", "password": PASSWORD}).status_code == 404


def test_a_company_signs_up_and_its_creators_join_with_the_code(open_client):
    c = open_client
    made = _company(c)
    assert made.status_code == 201, made.text
    boss = made.json()
    assert boss["user"]["role"] == "brand_admin" and boss["company"] == "Leafco" and len(boss["join_code"]) == 8
    # A real workspace: the built-in rules are there, and nothing else.
    assert len(c.get("/rules", headers=_auth(boss["token"])).json()) > 20
    assert c.get("/contents", headers=_auth(boss["token"])).json() == []
    assert c.get("/accounts/join-code", headers=_auth(boss["token"])).json()["join_code"] == boss["join_code"]

    joined = c.post("/accounts/signup", json={"kind": "creator", "join_code": boss["join_code"].lower(),
                                              "name": "Ravi", "email": "ravi@mail.example", "password": PASSWORD})
    assert joined.status_code == 201, joined.text
    ravi = joined.json()
    assert ravi["user"]["role"] == "creator" and ravi["join_code"] is None and ravi["company"] == "Leafco"
    people = {u["name"] for u in c.get("/users", headers=_auth(boss["token"])).json()}
    assert people == {"Mira", "Ravi"}
    # A creator can't read the join code, and a wrong code joins nothing.
    assert c.get("/accounts/join-code", headers=_auth(ravi["token"])).status_code == 404
    assert c.post("/accounts/signup", json={"kind": "creator", "join_code": "NOPE2345", "name": "X",
                                            "email": "x@mail.example", "password": PASSWORD}).status_code == 404


def test_password_sign_in_replaces_the_token_and_wrong_passwords_pause(open_client):
    c = open_client
    first = _company(c).json()["token"]
    ok = c.post("/accounts/signin", json={"email": "MIRA@leafco.example", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["join_code"]
    assert c.get("/me", headers=_auth(ok.json()["token"])).status_code == 200
    assert c.get("/me", headers=_auth(first)).status_code == 401  # the old session is signed out
    for _ in range(8):
        assert c.post("/accounts/signin", json={"email": "mira@leafco.example", "password": "wrong password!"}
                      ).status_code == 401
    assert c.post("/accounts/signin", json={"email": "mira@leafco.example", "password": PASSWORD}).status_code == 429
    # Unknown emails get the same answer as a wrong password.
    assert c.post("/accounts/signin", json={"email": "nobody@x.example", "password": PASSWORD}).status_code == 401


def test_emails_are_unique_and_passwords_have_a_floor(open_client):
    c = open_client
    assert _company(c).status_code == 201
    assert _company(c, email="Mira@LeafCo.example", name="Other").status_code == 409
    weak = c.post("/accounts/signup", json={"kind": "company", "company_name": "Weak", "name": "W",
                                            "email": "w@weak.example", "password": "short"})
    assert weak.status_code == 422


def test_seeded_workspaces_cannot_be_joined_by_code(open_client):
    c = open_client
    boot = c.post("/bootstrap", json={"workspace_name": "Seeded", "admin_email": "a@seeded.example",
                                      "admin_name": "A"})
    assert boot.status_code == 201
    assert c.get("/accounts/join-code", headers=_auth(boot.json()["token"])).status_code == 404
    # A token-only account has no password to sign in with.
    assert c.post("/accounts/signin", json={"email": "a@seeded.example", "password": PASSWORD}).status_code == 401


def test_companies_are_capped_and_self_serve_reviews_have_a_daily_allowance(open_client):
    c = open_client
    tokens = [_company(c, email=f"m{i}@co{i}.example", name=f"Co {i}").json()["token"] for i in range(3)]
    assert _company(c, email="late@co.example", name="Late").status_code == 503
    h = _auth(tokens[0])
    # Every route that spends model calls draws on one daily budget, so a new version can't dodge it.
    first = c.post("/contents", headers=h, json={"title": "Post", "channel": "linkedin", "body": "Hello there."})
    assert first.status_code == 201, first.text
    cid = first.json()["content"]["id"]
    for _ in range(2):
        assert c.post(f"/contents/{cid}/versions", headers=h, json={"body": "Hello again."}).status_code == 201
    over = c.post(f"/contents/{cid}/versions", headers=h, json={"body": "And again."})
    assert over.status_code == 429 and "checks for today" in over.json()["detail"]
    assert c.post("/assistant/context", headers=h, json={"messages": ["what is new?"]}).status_code == 429
    # Other companies have their own allowance; seeded workspaces have none.
    assert c.post("/contents", headers=_auth(tokens[1]), json={"title": "P", "channel": "linkedin",
                                                               "body": "Hi."}).status_code == 201
