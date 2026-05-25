"""Sync LiveKit SIP trunks and dispatch rules into the VBots database."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_agent import AIAgent
from app.db.models.dispatch_rule import DispatchRule, DispatchType
from app.db.models.sip_trunk import SIPTrunk, TrunkDirection, TrunkStatus
from app.services.livekit_service import livekit_service


def _trunk_id(trunk: Any) -> str:
    return getattr(trunk, "sip_trunk_id", None) or getattr(trunk, "id", "") or ""


def _trunk_name(trunk: Any) -> str:
    return getattr(trunk, "name", None) or _trunk_id(trunk) or "LiveKit Trunk"


def _trunk_numbers(trunk: Any) -> str:
    numbers = getattr(trunk, "numbers", None) or []
    return ",".join(str(n) for n in numbers)


async def sync_sip_trunks_from_livekit(db: AsyncSession, client_id: int) -> dict[str, int]:
    """Import inbound/outbound trunks from LiveKit into sip_trunks table."""
    created = updated = 0

    for list_fn, direction in (
        (livekit_service.list_inbound_trunks, TrunkDirection.INBOUND),
        (livekit_service.list_outbound_trunks, TrunkDirection.OUTBOUND),
    ):
        try:
            response = await list_fn()
        except Exception as e:
            return {"created": created, "updated": updated, "error": str(e)}

        items = getattr(response, "items", None) or []
        for lk_trunk in items:
            lk_id = _trunk_id(lk_trunk)
            if not lk_id:
                continue

            result = await db.execute(
                select(SIPTrunk).where(
                    SIPTrunk.client_id == client_id,
                    SIPTrunk.livekit_trunk_id == lk_id,
                )
            )
            existing = result.scalar_one_or_none()
            numbers = _trunk_numbers(lk_trunk)
            sip_uri = getattr(lk_trunk, "sip_uri", None) or f"livekit://{lk_id}"

            if existing:
                existing.name = _trunk_name(lk_trunk)
                existing.did_numbers = numbers or existing.did_numbers
                existing.sip_uri = sip_uri
                existing.status = TrunkStatus.ACTIVE
                existing.direction = direction
                updated += 1
            else:
                db.add(
                    SIPTrunk(
                        client_id=client_id,
                        name=_trunk_name(lk_trunk),
                        direction=direction,
                        status=TrunkStatus.ACTIVE,
                        sip_uri=sip_uri,
                        did_numbers=numbers,
                        livekit_trunk_id=lk_id,
                        auth_username=getattr(lk_trunk, "auth_username", None),
                    )
                )
                created += 1

    await db.flush()
    return {"created": created, "updated": updated}


async def sync_dispatch_rules_from_livekit(db: AsyncSession, client_id: int) -> dict[str, int]:
    """Import dispatch rules from LiveKit into dispatch_rules table."""
    created = skipped = 0

    try:
        response = await livekit_service.list_dispatch_rules()
    except Exception as e:
        return {"created": created, "skipped": skipped, "error": str(e)}

    items = getattr(response, "items", None) or []
    agents_result = await db.execute(select(AIAgent).where(AIAgent.client_id == client_id))
    agents = agents_result.scalars().all()
    default_agent = agents[0] if agents else None

    for lk_rule in items:
        rule_id = getattr(lk_rule, "sip_dispatch_rule_id", None) or getattr(lk_rule, "id", "")
        if not rule_id:
            continue

        existing = await db.execute(
            select(DispatchRule).where(
                DispatchRule.client_id == client_id,
                DispatchRule.livekit_rule_id == rule_id,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        metadata_raw = getattr(lk_rule, "metadata", None) or "{}"
        try:
            metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
        except json.JSONDecodeError:
            metadata = {}

        agent_id = metadata.get("agent_id")
        if agent_id:
            agent_check = await db.execute(
                select(AIAgent).where(AIAgent.id == agent_id, AIAgent.client_id == client_id)
            )
            if not agent_check.scalar_one_or_none():
                agent_id = None

        if not agent_id and default_agent:
            agent_id = default_agent.id

        if not agent_id:
            skipped += 1
            continue

        trunk_ids = getattr(lk_rule, "trunk_ids", None) or []
        sip_trunk_id = None
        match_value = rule_id
        if trunk_ids:
            trunk_result = await db.execute(
                select(SIPTrunk).where(
                    SIPTrunk.client_id == client_id,
                    SIPTrunk.livekit_trunk_id == trunk_ids[0],
                )
            )
            trunk = trunk_result.scalar_one_or_none()
            if trunk:
                sip_trunk_id = trunk.id
                match_value = trunk.did_numbers or trunk.name or trunk_ids[0]

        room_prefix = ""
        rule_obj = getattr(lk_rule, "rule", None)
        if rule_obj:
            individual = getattr(rule_obj, "dispatch_rule_individual", None)
            if individual:
                room_prefix = getattr(individual, "room_prefix", "") or ""

        db.add(
            DispatchRule(
                client_id=client_id,
                agent_id=agent_id,
                rule_type=DispatchType.TRUNK,
                match_value=match_value,
                priority=0,
                sip_trunk_id=sip_trunk_id,
                livekit_rule_id=rule_id,
            )
        )
        created += 1

    await db.flush()
    return {"created": created, "skipped": skipped}
