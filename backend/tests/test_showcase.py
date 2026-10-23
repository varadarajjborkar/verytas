"""The demo companies seed through the real API, stay apart from each other, and write the sign-in file."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from verytas.config import Settings
from verytas.main import create_app
from verytas.showcase import engine, seed
from verytas.showcase import kitepath as kp
from verytas.showcase.art import emblem, lockup
from verytas.showcase.spec import CLEAN, Company, Member, Piece

PIECES_PER_COMPANY = 6  # a smaller seed; the CLI seeds every piece


def _stub() -> Company:
    """A second, tiny company, so isolation is tested even before every real company is written."""
    team = [Member("admin", "head@stubco.example", "Head Stub", "brand_admin"),
            Member("approver", "mgr@stubco.example", "Mgr Stub", "approver"),
            Member("reviewer", "rev@stubco.example", "Rev Stub", "reviewer"),
            Member("auditor", "aud@stubco.example", "Aud Stub", "auditor")]
    maker = Member("maya", "maya@stubco.example", "Maya", "creator", "careful")
    rule = {"code": "STUB-SECRET", "category": "terminology", "kind": "deterministic", "severity": "must",
            "title": "Stub only", "text": "Write Stubco in full.", "pattern": {"type": "casing", "terms": ["Stubco"]}}
    return Company(
        key="stub", brand="Stubco", industry="Testing", domain="stubco.example", days=10, team=team, creators=[maker],
        rules=[rule], facts=[], terms=[], contacts=[],
        assets=[{"name": "Stub logo", "kind": "logo", "image": lambda: lockup(emblem("hex", 200, (200, 30, 30), (150, 20, 20), (255, 255, 255)), "Stubco", (150, 20, 20)).convert("RGBA")},
                {"name": "Old stub logo", "kind": "logo", "retired": True,
                 "image": lambda: emblem("sun", 300, (30, 140, 90), (20, 100, 70), (250, 220, 120))},
                {"name": "Rival", "kind": "competitor",
                 "image": lambda: emblem("shield", 300, (20, 20, 120), (10, 10, 80), (250, 220, 120))}],
        events=[], people=[],
        pieces=lambda: [Piece("s1", "maya", "Hello", "x", "Stubco says hello to everyone.", 5, CLEAN),
                        Piece("s2", "maya", "Draft", "x", "A quiet draft.", 3, [])],
        demo=[("admin", "admin", "manager", "Head of brand", "Owns the library."),
              ("c0", "maya", "creator", "Creator", "Writes posts.")])


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("showcase")
    real = engine.load
    engine.load = lambda only=None: [*real(only), _stub()]
    try:
        accounts = tmp / "accounts.json"
        counts = seed(tmp / "show.db", tmp / "keys", None, accounts, limit=PIECES_PER_COMPANY)
    finally:
        engine.load = real
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp / 'show.db'}", llm_mode="offline", keys_dir=tmp / "keys",
                        faces_enabled=False)
    doc = json.loads(accounts.read_text())
    with TestClient(create_app(settings)) as client:
        yield client, doc, counts


def _h(doc: dict, brand: str, key: str) -> dict:
    co = next(c for c in doc["companies"] if c["brand"] == brand)
    return {"Authorization": "Bearer " + next(p["token"] for p in co["people"] if p["key"] == key)}


def test_each_company_has_its_own_workspace_and_counts(seeded):
    client, doc, counts = seeded
    assert set(counts["companies"]) >= {"Kitepath", "Stubco"}
    for brand in counts["companies"]:
        h = _h(doc, brand, "admin")
        assert client.get("/me", headers=h).status_code == 200
        assert len(client.get("/rules", headers=h).json()) > 25  # the built-in rules plus the company's own
        assert counts["companies"][brand]["pieces"] > 0
    kit = _h(doc, "Kitepath", "admin")
    assert len([r for r in client.get("/rules", headers=kit).json() if not r["system"]]) >= 18
    assert len(client.get("/facts", headers=kit).json()) >= 8


def test_a_creator_cannot_read_another_companys_content_or_rules(seeded):
    client, doc, _ = seeded
    mine = _h(doc, "Stubco", "c0")
    theirs = _h(doc, "Kitepath", "admin")
    other = client.get("/contents", headers=theirs).json()
    assert other, "the other company has content"
    for item in other[:5]:
        assert client.get(f"/contents/{item['id']}", headers=mine).status_code == 404
    codes = {r["code"] for r in client.get("/rules", headers=mine).json()}
    assert "STUB-SECRET" in codes and "TERM-NAME" not in codes
    assert not any(c["title"] == "Thank you, learners" for c in client.get("/contents", headers=mine).json())
    assert "STUB-SECRET" not in {r["code"] for r in client.get("/rules", headers=theirs).json()}


def test_retired_and_competitor_assets_are_registered(seeded):
    client, doc, _ = seeded
    for brand in ("Kitepath", "Stubco"):
        assets = client.get("/brand-assets", headers=_h(doc, brand, "admin")).json()
        assert any(a["retired"] for a in assets), brand
        assert any(a["kind"] == "competitor" for a in assets), brand
    kinds = {a["kind"] for a in client.get("/brand-assets", headers=_h(doc, "Kitepath", "admin")).json()}
    assert {"logo", "wordmark", "icon", "mascot", "packaging", "pattern", "partner", "competitor"} <= kinds


def test_accounts_file_keeps_the_old_keys_and_lists_every_company(seeded):
    _, doc, _ = seeded
    assert doc["brand"] == "Kitepath" and "seeded_at" in doc
    assert [p["key"] for p in doc["people"]] == ["approver", "admin", "c2", "c1", "c6"]
    assert set(doc["people"][0]) == {"key", "name", "side", "title", "blurb", "token"}
    assert doc["companies"][0]["people"] == doc["people"]
    for co in doc["companies"]:
        assert {"brand", "industry", "people"} <= set(co) and co["people"]


def test_kitepath_is_deterministic():
    a = [(p.key, p.title, p.body, p.days_ago) for p in kp.build().pieces()]
    b = [(p.key, p.title, p.body, p.days_ago) for p in kp.build().pieces()]
    assert a == b and len(a) >= 100


def test_accounts_file_is_owner_only_even_over_an_old_open_file(tmp_path):
    import stat

    co = kp.build()
    tokens = {mk: "t" for _, mk, _, _, _ in co.demo}
    path = tmp_path / "accounts.json"
    path.write_text("{}")
    path.chmod(0o644)  # left by an older seed
    engine._demo_accounts(path, [(co, tokens)])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["brand"] == co.brand


def test_an_unknown_company_name_is_refused_by_name():
    with pytest.raises(SystemExit, match="kitepth"):
        engine.load(["kitepth"])
