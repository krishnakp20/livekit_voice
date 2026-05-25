import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AdminUser, CurrentUser, DbSession

logger = logging.getLogger("vbots.dispatch")
from app.db.models.ai_agent import AIAgent
from app.db.models.dispatch_rule import DispatchRule, DispatchType
from app.db.models.sip_trunk import SIPTrunk
from app.schemas.dispatch import DispatchRuleCreate, DispatchRuleResponse, DispatchRuleUpdate
from app.services.livekit_service import livekit_service
from app.services.sync_service import sync_dispatch_rules_from_livekit

router = APIRouter()


def _agent_metadata(agent: AIAgent, client_id: int, rule: DispatchRule) -> dict:
    return {
        "agent_id": agent.id,
        "client_id": client_id,
        "name": agent.name,
        "language": agent.language.value,
        "voice": agent.voice,
        "called_number": rule.match_value if rule.rule_type == DispatchType.DID else None,
        "did": rule.match_value if rule.rule_type == DispatchType.DID else None,
    }


async def _get_rule(db: DbSession, rule_id: int, client_id: int) -> DispatchRule:
    result = await db.execute(
        select(DispatchRule).where(DispatchRule.id == rule_id, DispatchRule.client_id == client_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


async def _apply_rule_to_livekit(db: DbSession, rule: DispatchRule, client_id: int) -> str:
    """Push agent dispatch to LiveKit for this rule. Returns status message."""
    agent_result = await db.execute(
        select(AIAgent).where(AIAgent.id == rule.agent_id, AIAgent.client_id == client_id)
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    trunk = None
    if rule.sip_trunk_id:
        trunk_result = await db.execute(select(SIPTrunk).where(SIPTrunk.id == rule.sip_trunk_id))
        trunk = trunk_result.scalar_one_or_none()

    metadata = _agent_metadata(agent, client_id, rule)

    if rule.livekit_rule_id:
        try:
            response = await livekit_service.list_dispatch_rules()
            items = list(getattr(response, "items", None) or [])
            lk_rule = next(
                (
                    r
                    for r in items
                    if getattr(r, "sip_dispatch_rule_id", None) == rule.livekit_rule_id
                ),
                None,
            )
            if lk_rule:
                await livekit_service.update_dispatch_rule_agent(lk_rule, metadata)
                return "LiveKit dispatch rule updated"
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LiveKit update failed: {e}") from e
        raise HTTPException(status_code=404, detail="LiveKit rule not found on server")

    if trunk and trunk.livekit_trunk_id:
        try:
            lk_rule_id = await livekit_service.create_dispatch_rule(
                trunk_id=trunk.livekit_trunk_id,
                room_prefix=f"agent-{agent.id}",
                agent_metadata=metadata,
                inbound_numbers=[rule.match_value] if rule.rule_type == DispatchType.DID else None,
            )
            rule.livekit_rule_id = lk_rule_id
            await db.flush()
            return "LiveKit dispatch rule created"
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LiveKit create failed: {e}") from e

    raise HTTPException(
        status_code=400,
        detail="Link a SIP trunk with LiveKit trunk id, or sync rules from LiveKit first",
    )


@router.get("", response_model=list[DispatchRuleResponse])
async def list_rules(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(DispatchRule)
        .where(DispatchRule.client_id == current_user.client_id)
        .order_by(DispatchRule.priority.desc())
    )
    return result.scalars().all()


@router.post("", response_model=DispatchRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(data: DispatchRuleCreate, db: DbSession, current_user: AdminUser):
    agent_result = await db.execute(
        select(AIAgent).where(AIAgent.id == data.agent_id, AIAgent.client_id == current_user.client_id)
    )
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    rule = DispatchRule(client_id=current_user.client_id, **data.model_dump())
    db.add(rule)
    await db.flush()

    trunk = None
    if data.sip_trunk_id:
        trunk_result = await db.execute(select(SIPTrunk).where(SIPTrunk.id == data.sip_trunk_id))
        trunk = trunk_result.scalar_one_or_none()

    if trunk and trunk.livekit_trunk_id:
        agent = (await db.execute(select(AIAgent).where(AIAgent.id == data.agent_id))).scalar_one()
        try:
            rule.livekit_rule_id = await livekit_service.create_dispatch_rule(
                trunk_id=trunk.livekit_trunk_id,
                room_prefix=f"agent-{agent.id}",
                agent_metadata=_agent_metadata(agent, current_user.client_id, rule),
                inbound_numbers=[data.match_value] if data.rule_type == DispatchType.DID else None,
            )
            logger.info(
                "Created LiveKit dispatch rule %s for agent=%s trunk=%s",
                rule.livekit_rule_id,
                agent.id,
                trunk.livekit_trunk_id,
            )
        except Exception as e:
            logger.error(
                "LiveKit dispatch rule NOT created for agent=%s trunk=%s: %s — "
                "use 'Apply to LiveKit' button on the rule after fixing the error.",
                agent.id,
                trunk.livekit_trunk_id,
                e,
            )

    await db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=DispatchRuleResponse)
async def update_rule(
    rule_id: int,
    data: DispatchRuleUpdate,
    db: DbSession,
    current_user: AdminUser,
    apply_livekit: bool = False,
):
    """Update dispatch mapping. Set apply_livekit=true to push agent to LiveKit."""
    rule = await _get_rule(db, rule_id, current_user.client_id)

    if data.agent_id is not None:
        agent_result = await db.execute(
            select(AIAgent).where(
                AIAgent.id == data.agent_id, AIAgent.client_id == current_user.client_id
            )
        )
        if not agent_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Agent not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)

    await db.flush()

    if apply_livekit:
        await _apply_rule_to_livekit(db, rule, current_user.client_id)

    await db.refresh(rule)
    return rule


@router.post("/{rule_id}/apply-livekit")
async def apply_rule_livekit(rule_id: int, db: DbSession, current_user: AdminUser):
    """Push current agent mapping to LiveKit without changing other fields."""
    rule = await _get_rule(db, rule_id, current_user.client_id)
    message = await _apply_rule_to_livekit(db, rule, current_user.client_id)
    await db.refresh(rule)
    return {"message": message, "rule": DispatchRuleResponse.model_validate(rule)}


@router.post("/apply-all-livekit")
async def apply_all_rules_livekit(db: DbSession, current_user: AdminUser):
    """Re-push every dispatch rule to LiveKit (fixes empty agent_name on SIP rules)."""
    result = await db.execute(
        select(DispatchRule).where(DispatchRule.client_id == current_user.client_id)
    )
    rules = result.scalars().all()
    applied: list[str] = []
    errors: list[str] = []
    for rule in rules:
        try:
            msg = await _apply_rule_to_livekit(db, rule, current_user.client_id)
            applied.append(f"rule {rule.id}: {msg}")
        except HTTPException as e:
            errors.append(f"rule {rule.id}: {e.detail}")
        except Exception as e:
            errors.append(f"rule {rule.id}: {e}")
    return {"applied": applied, "errors": errors}


@router.post("/sync-from-livekit")
async def sync_from_livekit(db: DbSession, current_user: CurrentUser):
    """Import dispatch rules created in LiveKit console into VBots database."""
    if current_user.client_id is None:
        raise HTTPException(status_code=400, detail="User has no client assigned")
    result = await sync_dispatch_rules_from_livekit(db, current_user.client_id)
    return {"message": "Sync complete", **result}


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, db: DbSession, current_user: AdminUser):
    rule = await _get_rule(db, rule_id, current_user.client_id)
    await db.delete(rule)
