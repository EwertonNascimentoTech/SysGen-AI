from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_session
from app.models.governance_advance_rule import GovernanceAdvanceRule
from app.models.user import User
from app.schemas.governance_rule import GovernanceRuleCreate, GovernanceRuleOut, GovernanceRulePatch
from app.services.audit import log_action
from app.services.governance_catalog import RULE_KEYS

router = APIRouter(prefix="/governance-advance-rules", tags=["governance-advance-rules"])


@router.get("", response_model=list[GovernanceRuleOut])
async def list_rules(
    _: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(GovernanceAdvanceRule).order_by(GovernanceAdvanceRule.name))
    return list(result.scalars().all())


@router.post("", response_model=GovernanceRuleOut)
async def create_rule(
    body: GovernanceRuleCreate,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    r = GovernanceAdvanceRule(
        name=body.name.strip(),
        description=(body.description.strip() if body.description else None) or None,
        rule_key=body.rule_key.strip(),
        min_tags_value=body.min_tags_value if body.rule_key == "min_tag_count" else None,
        active=body.active,
        on_violation=body.on_violation,
    )
    session.add(r)
    await session.flush()
    await log_action(
        session,
        actor_email=user.email,
        action="governance_rule.create",
        entity_type="governance_advance_rule",
        entity_id=r.id,
        detail=r.name,
    )
    await session.commit()
    await session.refresh(r)
    return r


@router.patch("/{rule_id}", response_model=GovernanceRuleOut)
async def patch_rule(
    rule_id: int,
    body: GovernanceRulePatch,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    r = await session.get(GovernanceAdvanceRule, rule_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada")
    rk = body.rule_key if body.rule_key is not None else r.rule_key
    if rk not in RULE_KEYS:
        raise HTTPException(status_code=400, detail=f"rule_key inválido: {rk}")
    if body.name is not None:
        r.name = body.name.strip()
    if body.description is not None:
        r.description = body.description.strip() or None
    if body.rule_key is not None:
        r.rule_key = body.rule_key.strip()
    if body.active is not None:
        r.active = body.active
    if body.on_violation is not None:
        r.on_violation = body.on_violation
    if body.min_tags_value is not None:
        r.min_tags_value = body.min_tags_value
    elif body.rule_key is not None and body.rule_key != "min_tag_count":
        r.min_tags_value = None
    if r.rule_key == "min_tag_count":
        if not r.min_tags_value or r.min_tags_value < 1:
            raise HTTPException(status_code=400, detail="min_tags_value obrigatório para min_tag_count")
    else:
        r.min_tags_value = None
    await log_action(
        session,
        actor_email=user.email,
        action="governance_rule.patch",
        entity_type="governance_advance_rule",
        entity_id=r.id,
    )
    await session.commit()
    await session.refresh(r)
    return r


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    user: User = Depends(require_roles("admin", "coordenador")),
    session: AsyncSession = Depends(get_session),
):
    r = await session.get(GovernanceAdvanceRule, rule_id)
    if not r:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada")
    await session.delete(r)
    await log_action(
        session,
        actor_email=user.email,
        action="governance_rule.delete",
        entity_type="governance_advance_rule",
        entity_id=rule_id,
    )
    await session.commit()
