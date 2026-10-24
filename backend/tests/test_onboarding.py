"""First steps: the checklist reads the workspace, and the sample kit fills only an empty library."""

from __future__ import annotations


def _admin(client) -> dict:
    token = client.post("/bootstrap", json={"workspace_name": "Acme", "admin_email": "a@acme.io",
                                            "admin_name": "Ana"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_new_company_sees_what_to_set_up_and_can_load_the_sample_kit(client):
    h = _admin(client)
    first = client.get("/onboarding", headers=h).json()
    assert first["company"] == "Acme" and first["sample_kit"] is True
    assert [s["key"] for s in first["steps"]] == ["material", "facts", "terms", "assets", "creator", "review"]
    # Built-in rules come with every workspace and are not the company's own material.
    assert not any(s["done"] for s in first["steps"])

    made = client.post("/onboarding/sample-kit", headers=h)
    assert made.status_code == 201, made.text
    counts = made.json()
    assert counts["rules"] > 5 and counts["facts"] > 5 and counts["terms"] and counts["assets"]
    after = client.get("/onboarding", headers=h).json()
    done = {s["key"]: s["done"] for s in after["steps"]}
    assert done["material"] and done["facts"] and done["terms"] and done["assets"] and not done["creator"]
    assert after["sample_kit"] is False
    # Rules arrive active, and superseded facts keep their chain: only one price is current.
    rules = client.get("/rules", headers=h).json()
    assert any(r["code"] == "TONE-URGENCY" and r["status"] == "active" for r in rules)
    prices = [f for f in client.get("/facts", headers=h).json() if f["subject"] == "annual plan price"]
    old, new = sorted(prices, key=lambda f: f["valid_from"])
    assert new["supersedes_id"] == old["id"] and new["value"] == 4999
    # Never twice, and never into a library that has anything of its own.
    assert client.post("/onboarding/sample-kit", headers=h).status_code == 409


def test_steps_follow_the_role_and_only_an_admin_loads_the_kit(client):
    h = _admin(client)
    creator = client.post("/users", headers=h, json={"email": "c@acme.io", "name": "Cy", "role": "creator"}).json()
    ch = {"Authorization": f"Bearer {creator['token']}"}
    mine = client.get("/onboarding", headers=ch).json()
    assert mine["role"] == "creator" and mine["sample_kit"] is False
    assert [s["key"] for s in mine["steps"]] == ["submit", "fix", "ask"]
    assert client.post("/onboarding/sample-kit", headers=ch).status_code == 403
    assert {s["key"]: s["done"] for s in client.get("/onboarding", headers=h).json()["steps"]}["creator"]

    reviewer = client.post("/users", headers=h, json={"email": "r@acme.io", "name": "Ravi",
                                                      "role": "reviewer"}).json()
    team = client.get("/onboarding", headers={"Authorization": f"Bearer {reviewer['token']}"}).json()
    assert [s["key"] for s in team["steps"]] == ["decide", "ask"]
