from __future__ import annotations

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
        ))
    await session.flush()
    await append(session, workspace_id=ws.id, actor=f"user:{admin.id}", action="workspace.created",
                 object_type="workspace", object_id=ws.id, detail={"system_rules": len(SYSTEM_RULES)})
    return ws, admin, token
