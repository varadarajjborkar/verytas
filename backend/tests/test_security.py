from __future__ import annotations

import os
import stat

import pytest
from pydantic import BaseModel
from sqlalchemy import update

from verytas.db import Database
from verytas.models import AuditEntry, Workspace
from verytas.providers.base import Answer, Question
from verytas.security.audit import append, verify_chain
from verytas.security.redaction import RedactingJudge, RedactingLLM, Redactor
from verytas.security.signing import AgentKeyring


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    await database.create_all()
    yield database
    await database.dispose()


async def _workspace(s) -> int:
    ws = Workspace(name="Acme")
    s.add(ws)
    await s.flush()
    return ws.id


async def test_audit_chain_verifies_and_detects_tampering(db):
    async with db.sessionmaker() as s:
        ws = await _workspace(s)
        for i in range(4):
            await append(s, workspace_id=ws, actor="user:1", action="rule.update", object_type="rule",
                         object_id=i, detail={"field": "text", "n": i})
        await s.commit()
        assert (await verify_chain(s, ws)).ok

        await s.execute(update(AuditEntry).where(AuditEntry.id == 2).values(detail={"field": "forged"}))
        await s.commit()
        report = await verify_chain(s, ws)
        assert not report.ok and report.first_bad_id == 2 and "altered" in report.reason


async def test_audit_chain_detects_deleted_entry(db):
    async with db.sessionmaker() as s:
        ws = await _workspace(s)
        for i in range(3):
            await append(s, workspace_id=ws, actor="system", action="x", object_type="y", object_id=i)
        await s.commit()
        await s.delete(await s.get(AuditEntry, 2))
        await s.commit()
        report = await verify_chain(s, ws)
        assert not report.ok and report.first_bad_id == 3 and "link broken" in report.reason


async def test_chains_are_per_workspace(db):
    async with db.sessionmaker() as s:
        a, b = await _workspace(s), await _workspace(s)
        e1 = await append(s, workspace_id=a, actor="s", action="x", object_type="y")
        e2 = await append(s, workspace_id=b, actor="s", action="x", object_type="y")
        await s.commit()
        assert e1.prev_hash == e2.prev_hash == "0" * 64


def test_signatures_verify_and_reject_edits(tmp_path):
    ring = AgentKeyring(tmp_path / "keys")
    payload = {"title": "Claim conflicts", "confidence": 0.9, "fact_id": 2}
    sig = ring.sign("claims-worker", payload)
    assert ring.verify(sig, payload)
    assert not ring.verify(sig, {**payload, "confidence": 0.1})
    assert not ring.verify(sig.replace("claims-worker", "tone-worker"), payload)
    assert not ring.verify("garbage", payload)


def test_keys_persist_with_owner_only_permissions(tmp_path):
    keys = tmp_path / "keys"
    sig = AgentKeyring(keys).sign("judge", {"a": 1})
    assert AgentKeyring(keys).verify(sig, {"a": 1})  # fresh keyring loads the same key
    mode = stat.S_IMODE(os.stat(keys / "judge.pem").st_mode)
    assert mode == 0o600


def test_keyring_rejects_path_like_roles(tmp_path):
    with pytest.raises(ValueError):
        AgentKeyring(tmp_path).sign("../etc/passwd", {})


def test_redactor_round_trip():
    r = Redactor(["Project Lumen", "Lumen"])
    text = "Project Lumen launches; email jane@acme.io or call +91 98765 43210. Lumen rocks. Dated 2026-10-20."
    red = r.redact(text)
    for secret in ("Project Lumen", "jane@acme.io", "98765"):
        assert secret not in red
    assert "2026-10-20" in red  # dates are not phone numbers
    assert "[[TERM_1]]" in red and "[[TERM_2]]" in red
    assert r.restore(red) == text


class Out(BaseModel):
    quote: str


class Task:
    name, system, schema, fast = "t", "s", Out, True

    def user_content(self):
        return "The codename is Project Lumen."

    def heuristic(self):
        return Out(quote="")


async def test_redacting_llm_hides_terms_and_restores_reply():
    seen = {}

    class Spy:
        name = "spy"

        async def run(self, task):
            seen["content"] = task.user_content()
            return Out(quote=seen["content"].split("is ")[1].rstrip("."))

    out = await RedactingLLM(Spy(), Redactor(["Project Lumen"])).run(Task())
    assert "Project Lumen" not in seen["content"]
    assert out.quote == "Project Lumen"


async def test_redacting_judge_hides_terms_in_state_and_questions():
    seen = {}

    class Spy:
        name = "spy"

        async def ask(self, state, questions):
            seen["state"], seen["q"] = state, questions
            return {k: Answer("noul", 0.1) for k in questions}

    judge = RedactingJudge(Spy(), Redactor(["Project Lumen"]))
    await judge.ask({"claim": "Project Lumen is live"},
                    {"q": Question("noul", "Is Project Lumen mentioned?", {"true": "Project Lumen", "false": "no"})})
    blob = repr(seen)
    assert "Project Lumen" not in blob and "[[TERM_1]]" in blob


# --- regression tests for errcheck findings ------------------------------------

@pytest.mark.parametrize("text", ["Project-Lumen", "project_lumen", "ProjectLumen", "Project  Lumen",
                                  "Project\nLumen", "Project Lumens", "the Project Lumen-X launch"])
def test_confidential_variants_are_redacted(text):
    r = Redactor(["Project Lumen"])
    assert "lumen" not in r.redact(text).lower()
    assert r.restore(r.redact(text)) == text


def test_leak_check_matches_variants_but_not_inside_other_words():
    from verytas.security.terms import term_pattern

    bounded = term_pattern("Zebra")
    assert bounded.search("pre-Zebra plans") and bounded.search("two zebras") and bounded.search("Zebra-2")
    assert not bounded.search("Zebrafish are fine")


async def test_concurrent_appends_do_not_fork_the_chain(db):
    import asyncio

    async with db.sessionmaker() as s:
        ws = await _workspace(s)
        await s.commit()

    async def writer(n):
        async with db.sessionmaker() as s:
            await append(s, workspace_id=ws, actor=f"w{n}", action="x", object_type="y")

    await asyncio.gather(*(writer(i) for i in range(8)))
    async with db.sessionmaker() as s:
        report = await verify_chain(s, ws)
    assert report.ok and report.entries == 8


def test_verify_never_mints_keys(tmp_path):
    keys = tmp_path / "keys"
    ring = AgentKeyring(keys)
    assert not ring.verify("ed25519:ghost:AAAA", {"a": 1})
    assert not (keys / "ghost.pem").exists()
