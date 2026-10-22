from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from verytas.db import Database
from verytas.models import (
    Content,
    ContentVersion,
    Fact,
    Finding,
    Level,
    Review,
    Role,
    User,
    Workspace,
)


@pytest.fixture
async def db(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}")
    await database.create_all()
    yield database
    await database.dispose()


async def _seed(session):
    ws = Workspace(name="Acme")
    session.add(ws)
    await session.flush()
    user = User(workspace_id=ws.id, email="a@acme.test", name="A", role=Role.creator, token_hash="x" * 64)
    session.add(user)
    await session.flush()
    content = Content(workspace_id=ws.id, title="Launch post", created_by=user.id)
    session.add(content)
    await session.flush()
    return ws, user, content


async def test_first_version_cannot_have_parent_and_later_versions_must(db):
    async with db.sessionmaker() as s:
        _, user, content = await _seed(s)
        v1 = ContentVersion(content_id=content.id, version_no=1, body="hi", created_by=user.id)
        s.add(v1)
        await s.flush()
        orphan = ContentVersion(
            content_id=content.id, version_no=2, parent_id=None, body="x", created_by=user.id
        )
        s.add(orphan)
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_findings_must_cite_a_rule_or_fact(db):
    async with db.sessionmaker() as s:
        _, user, content = await _seed(s)
        v1 = ContentVersion(content_id=content.id, version_no=1, body="hi", created_by=user.id)
        s.add(v1)
        await s.flush()
        review = Review(version_id=v1.id)
        s.add(review)
        await s.flush()
        s.add(Finding(
            review_id=review.id, unit_id="p1.s1", category="tone", level=Level.warning, title="t",
            explanation="e", confidence=0.5, checker="x", signature="sig",
        ))
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_fact_validity_window_must_be_forward(db):
    async with db.sessionmaker() as s:
        ws, _, _ = await _seed(s)
        s.add(Fact(workspace_id=ws.id, statement="s", source_ref="r",
                   valid_from=date(2026, 6, 1), valid_to=date(2026, 1, 1)))
        with pytest.raises(IntegrityError):
            await s.flush()


def test_fact_valid_on_is_half_open():
    f = Fact(statement="s", source_ref="r", valid_from=date(2026, 1, 1), valid_to=date(2026, 7, 1))
    assert f.valid_on(date(2026, 1, 1))
    assert f.valid_on(date(2026, 6, 30))
    assert not f.valid_on(date(2026, 7, 1))
