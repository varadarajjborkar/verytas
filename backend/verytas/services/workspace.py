from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from verytas.api.deps import new_token
from verytas.checks.system_rules import SYSTEM_RULES
from verytas.models import Role, Rule, RuleKind, RuleStatus, Severity, Tier, User, Workspace
from verytas.security.audit import append


async def create_workspace(session: AsyncSession, *, name: str, admin_email: str,
                           admin_name: str) -> tuple[Workspace, User, str]:
    ws = Workspace(name=name)
    session.add(ws)
    await session.flush()

    token, token_hash = new_token()
    admin = User(workspace_id=ws.id, email=admin_email, name=admin_name, role=Role.brand_admin,
                 clearance=Tier.confidential, token_hash=token_hash)
    session.add(admin)

    for spec in SYSTEM_RULES:
        session.add(Rule(
            workspace_id=ws.id, code=spec["code"], category=spec["category"], kind=RuleKind(spec["kind"]),
            severity=Severity(spec["severity"]), title=spec["title"], text=spec["text"],
            pattern=spec["pattern"], status=RuleStatus.active, system=True, source_ref="Verytas built-in",
            # Built-in rules hold no company secrets, and the tier ceiling only
            # applies a rule to content at or above its tier. Left at the
            # default "internal", public posts (the riskiest content) would
            # skip leak, claim and accessibility checks entirely.
            tier=Tier.public,
        ))
    await session.flush()
    await append(session, workspace_id=ws.id, actor=f"user:{admin.id}", action="workspace.created",
                 object_type="workspace", object_id=ws.id, detail={"system_rules": len(SYSTEM_RULES)})
    return ws, admin, token


async def backfill_system_rule_tiers(session: AsyncSession) -> int:
    """Workspaces created before built-in rules were seeded as public still have
    them at "internal", where the tier ceiling skips them on public content.
    Built-in rules carry no company data, so lifting them is always safe.
    Runs at startup; a no-op once every database is current."""
    result = await session.execute(
        update(Rule).where(Rule.system.is_(True), Rule.tier != Tier.public).values(tier=Tier.public)
    )
    await session.commit()
    return result.rowcount or 0
