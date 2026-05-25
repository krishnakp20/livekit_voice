"""Dial campaign leads via LiveKit SIP + agent worker (no broken Redis-only queue)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.call_log import CallDirection, CallLog, CallStatus
from app.db.models.campaign import Campaign, CampaignStatus, Lead, LeadStatus
from app.db.models.sip_trunk import SIPTrunk, TrunkDirection
from app.services.livekit_service import livekit_service

logger = logging.getLogger("vbots.campaign_dial")


from app.services.phone_utils import format_phone_for_sip, sip_participant_identity

async def get_outbound_livekit_trunk_id(db: AsyncSession, client_id: int) -> str:
    from app.core.config import settings

    # Fast path: env var avoids DB round-trip on every dial
    if settings.LIVEKIT_OUTBOUND_TRUNK_ID:
        return settings.LIVEKIT_OUTBOUND_TRUNK_ID

    result = await db.execute(
        select(SIPTrunk)
        .where(
            SIPTrunk.client_id == client_id,
            SIPTrunk.direction == TrunkDirection.OUTBOUND,
            SIPTrunk.is_active == True,
            SIPTrunk.livekit_trunk_id.isnot(None),
        )
        .order_by(SIPTrunk.id.asc())
        .limit(1)
    )
    trunk = result.scalar_one_or_none()
    if not trunk or not trunk.livekit_trunk_id:
        raise ValueError(
            "No outbound SIP trunk found. "
            "Go to SIP Trunks → create an Outbound trunk → Sync from LiveKit, "
            "then set LIVEKIT_OUTBOUND_TRUNK_ID=ST_xxx in .env for faster dialing."
        )
    return trunk.livekit_trunk_id


async def dial_campaign_leads(
    db: AsyncSession,
    campaign_id: int,
    *,
    limit: Optional[int] = None,
) -> dict:
    """
    Dial NEW leads for a RUNNING campaign.
    Creates LiveKit room with agent dispatch, call_log row, and SIP outbound dial.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise ValueError("Campaign not found")
    if campaign.status != CampaignStatus.RUNNING:
        raise ValueError("Campaign must be RUNNING to dial leads")

    batch = limit if limit is not None else max(1, campaign.dial_rate)
    leads_result = await db.execute(
        select(Lead)
        .where(Lead.campaign_id == campaign.id, Lead.status == LeadStatus.NEW)
        .order_by(Lead.id.asc())
        .limit(batch)
    )
    leads = leads_result.scalars().all()
    if not leads:
        return {"dialed": 0, "message": "No new leads to dial"}

    trunk_id = await get_outbound_livekit_trunk_id(db, campaign.client_id)
    dialed = 0
    errors: list[str] = []

    for lead in leads:
        phone = format_phone_for_sip(lead.phone)
        safe_phone = re.sub(r"\D", "", phone)
        # UUID suffix prevents collision when same number is retried or in multiple campaigns
        room_name = f"outbound-{campaign.agent_id}-{safe_phone}-{uuid.uuid4().hex[:8]}"

        meta = {
            "agent_id": campaign.agent_id,
            "client_id": campaign.client_id,
            "campaign_id": campaign.id,
            "lead_id": lead.id,
            "direction": "outbound",
        }

        try:
            await livekit_service.create_room_with_agent(room_name, meta)
            call = CallLog(
                client_id=campaign.client_id,
                agent_id=campaign.agent_id,
                campaign_id=campaign.id,
                lead_id=lead.id,
                room_name=room_name,
                callee_number=safe_phone,
                direction=CallDirection.OUTBOUND,
                status=CallStatus.RINGING,
            )
            db.add(call)
            await db.flush()

            await livekit_service.dial_participant(room_name, phone, trunk_id)
            lead.status = LeadStatus.DIALING
            dialed += 1
            logger.info(
                "Campaign %s dialed lead %s phone=%s room=%s call_id=%s",
                campaign.id,
                lead.id,
                phone,
                room_name,
                call.id,
            )
        except Exception as e:
            lead.status = LeadStatus.FAILED
            errors.append(f"lead {lead.id}: {e}")
            logger.exception("Failed to dial lead %s", lead.id)

    await db.commit()
    return {
        "dialed": dialed,
        "errors": errors,
        "trunk_id": trunk_id,
    }
