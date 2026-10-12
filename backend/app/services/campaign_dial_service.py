"""Dial campaign leads via LiveKit SIP + agent worker (no broken Redis-only queue)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_agent import AIAgent
from app.db.models.call_log import CallDirection, CallLog, CallStatus
from app.db.models.campaign import Campaign, CampaignStatus, Lead, LeadStatus
from app.db.models.client import Client
from app.db.models.sip_trunk import SIPTrunk, TrunkDirection
from app.services.livekit_service import livekit_service

logger = logging.getLogger("vbots.campaign_dial")

_DEFAULT_TZ = "Asia/Kolkata"


async def _client_timezone(db: AsyncSession, client_id: int) -> ZoneInfo:
    """Client.timezone (e.g. 'Asia/Kolkata') as a ZoneInfo, falling back safely."""
    tz_name = await db.scalar(select(Client.timezone).where(Client.id == client_id))
    try:
        return ZoneInfo(tz_name or _DEFAULT_TZ)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


async def is_within_calling_window(
    db: AsyncSession, client_id: int, campaign: Optional[Campaign], at: datetime
) -> bool:
    """True if `at` falls inside campaign's calling window, in the CLIENT's own
    local timezone (not server time). No window configured on the campaign
    (either hour is NULL) = unrestricted, always True — today's behaviour for
    every campaign that hasn't opted into a cadence."""
    if (
        not campaign
        or campaign.calling_window_start_hour is None
        or campaign.calling_window_end_hour is None
    ):
        return True
    tz = await _client_timezone(db, client_id)
    local_hour = at.astimezone(tz).hour
    return campaign.calling_window_start_hour <= local_hour < campaign.calling_window_end_hour


async def next_window_start(
    db: AsyncSession, client_id: int, campaign: Optional[Campaign], after: datetime
) -> datetime:
    """The next local-time window-start (e.g. tomorrow 9am IST) strictly after
    `after`, converted back to UTC for storage. If the window hasn't opened yet
    TODAY (e.g. `after` is 6am and the window starts at 9am), returns today's
    start instead of skipping a whole day. Falls back to hour 9 if no window is
    configured on the campaign (callers only use this once they've already
    decided a rollover is needed)."""
    tz = await _client_timezone(db, client_id)
    start_hour = (
        campaign.calling_window_start_hour
        if campaign and campaign.calling_window_start_hour is not None
        else 9
    )
    local_after = after.astimezone(tz)
    candidate = datetime.combine(local_after.date(), dtime(hour=start_hour), tzinfo=tz)
    if candidate <= local_after:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


async def compute_lead_retry_update(
    db: AsyncSession,
    lead: Lead,
    campaign: Optional[Campaign],
    now: datetime,
    failed: bool,
) -> None:
    """Mutate `lead` in place after a call that did NOT connect: retry_count always
    increments; status/next_attempt_at/day_count/attempts_today follow either the
    original immediate-retry behaviour (if the campaign hasn't set max_days > 1 or
    a calling window) or the day/window-aware cadence described on Campaign.

    Called once, from worker/agent.py's call-end handler — kept here rather than
    duplicated there so the dial-selection query and the retry logic can never
    disagree about what "eligible to call now" means.
    """
    max_retries = campaign.max_retries if campaign else 3
    retry_interval_minutes = campaign.retry_interval_minutes if campaign else 60
    max_days = campaign.max_days if campaign else 1
    window_configured = bool(
        campaign
        and campaign.calling_window_start_hour is not None
        and campaign.calling_window_end_hour is not None
    )

    lead.retry_count += 1
    cadence_enabled = max_days > 1 or window_configured

    if not cadence_enabled:
        # Unchanged legacy behaviour — every campaign that hasn't opted in keeps
        # retrying on the very next dial-loop poll, exactly as before.
        if lead.retry_count >= max_retries:
            lead.status = LeadStatus.NO_ANSWER if not failed else LeadStatus.FAILED
            logger.info(
                "Lead %s -> %s (retries=%s/%s)", lead.id, lead.status, lead.retry_count, max_retries
            )
        else:
            lead.status = LeadStatus.NEW
            logger.info(
                "Lead %s -> NEW for retry (attempt %s/%s)", lead.id, lead.retry_count, max_retries
            )
        return

    lead.attempts_today = (lead.attempts_today or 0) + 1
    candidate = now + timedelta(minutes=retry_interval_minutes)
    candidate_ok = await is_within_calling_window(db, lead.client_id, campaign, candidate)
    roll_to_next_day = lead.attempts_today >= max_retries or not candidate_ok

    if not roll_to_next_day:
        lead.next_attempt_at = candidate
        lead.status = LeadStatus.NEW
        logger.info(
            "Lead %s -> NEW, next_attempt_at=%s (attempt %s/%s today, day %s/%s)",
            lead.id, lead.next_attempt_at, lead.attempts_today, max_retries, lead.day_count, max_days,
        )
        return

    lead.day_count = (lead.day_count or 1) + 1
    lead.attempts_today = 0
    if lead.day_count > max_days:
        lead.status = LeadStatus.NO_ANSWER if not failed else LeadStatus.FAILED
        lead.next_attempt_at = None
        logger.info(
            "Lead %s -> %s (cadence exhausted: day %s/%s, total attempts=%s)",
            lead.id, lead.status, lead.day_count, max_days, lead.retry_count,
        )
        return

    # +1 minute: a candidate that landed exactly on the window boundary should
    # roll to TOMORROW's start, not resolve back to today's (next_window_start
    # returns today's start if `after` is still before it today).
    lead.next_attempt_at = await next_window_start(db, lead.client_id, campaign, now + timedelta(minutes=1))
    lead.status = LeadStatus.NEW
    logger.info(
        "Lead %s -> NEW, next_attempt_at=%s (rolled to day %s/%s)",
        lead.id, lead.next_attempt_at, lead.day_count, max_days,
    )


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

    now_utc = datetime.now(timezone.utc)
    if not await is_within_calling_window(db, campaign.client_id, campaign, now_utc):
        return {"dialed": 0, "message": "Outside campaign's calling window"}

    # ── Concurrency-aware batch size ────────────────────────────────────────
    # Auto-dialer goal: keep exactly `dial_rate` calls in progress at once.
    # in_flight = leads currently being called (status DIALING). We only top up
    # the difference, so as calls finish, the next leads are dialed — until none
    # remain, then the campaign auto-completes.
    in_flight = int(
        await db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.campaign_id == campaign.id, Lead.status == LeadStatus.DIALING)
        )
        or 0
    )
    if limit is not None:
        batch = limit
    else:
        batch = max(0, max(1, campaign.dial_rate) - in_flight)

    if batch <= 0:
        return {"dialed": 0, "message": f"At capacity ({in_flight} calls in progress)"}

    leads_result = await db.execute(
        select(Lead)
        .where(
            Lead.campaign_id == campaign.id,
            Lead.status == LeadStatus.NEW,
            (Lead.next_attempt_at.is_(None)) | (Lead.next_attempt_at <= now_utc),
        )
        .order_by(Lead.id.asc())
        .limit(batch)
    )
    leads = leads_result.scalars().all()
    if not leads:
        # Nothing eligible RIGHT NOW. Only auto-complete if there is truly no NEW
        # lead left at all (ignoring next_attempt_at) — otherwise a cadence lead
        # waiting for its scheduled next_attempt_at would get the campaign wrongly
        # marked COMPLETED instead of just "nothing to do on this poll".
        if in_flight == 0:
            any_new_left = await db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(Lead.campaign_id == campaign.id, Lead.status == LeadStatus.NEW)
            )
            if not any_new_left:
                campaign.status = CampaignStatus.COMPLETED
                await db.commit()
                logger.info("Campaign %s auto-completed — all leads dialed", campaign.id)
                return {"dialed": 0, "message": "Campaign completed — all leads dialed"}
            return {"dialed": 0, "message": f"{any_new_left} lead(s) waiting for next_attempt_at"}
        return {"dialed": 0, "message": f"No eligible leads; {in_flight} calls still in progress"}

    trunk_id = await get_outbound_livekit_trunk_id(db, campaign.client_id)

    # Required per-lead fields for this campaign's agent. A lead missing any of these
    # is skipped (marked FAILED) so the bot never runs with incomplete personalisation.
    agent = (
        await db.execute(select(AIAgent).where(AIAgent.id == campaign.agent_id))
    ).scalar_one_or_none()
    required_fields = [
        f.strip().lower()
        for f in ((agent.required_lead_fields or "") if agent else "").replace("\n", ",").split(",")
        if f.strip()
    ]

    dialed = 0
    skipped_missing = 0
    errors: list[str] = []
    seen_phones: set[str] = set()

    for lead in leads:
        # ── Required-field gate ──────────────────────────────────────────────
        if required_fields:
            try:
                lmeta = json.loads(lead.metadata_json) if lead.metadata_json else {}
            except (ValueError, TypeError):
                lmeta = {}
            missing = [
                f for f in required_fields
                if not str(lmeta.get(f, "")).strip()
            ]
            if missing:
                lead.status = LeadStatus.FAILED
                skipped_missing += 1
                errors.append(f"lead {lead.id}: missing required field(s): {', '.join(missing)}")
                logger.warning(
                    "Campaign %s: skipping lead %s — missing required field(s): %s",
                    campaign.id, lead.id, ", ".join(missing),
                )
                continue

        phone = format_phone_for_sip(lead.phone)
        safe_phone = re.sub(r"\D", "", phone)
        # dial_to carries the agent's dial_prefix tag (if any) for the live SIP leg only —
        # safe_phone/room_name/CallLog below stay on the real +91 number untouched.
        dial_to = phone
        if agent and agent.dial_prefix:
            dial_to = f"+{agent.dial_prefix}{phone[3:]}"

        if safe_phone in seen_phones:
            logger.warning(
                "Campaign %s: skipping duplicate phone %s (lead_id=%s) in this batch",
                campaign_id, safe_phone, lead.id,
            )
            continue
        seen_phones.add(safe_phone)
        # UUID suffix prevents collision when same number is retried or in multiple campaigns
        room_name = f"outbound-{campaign.agent_id}-{safe_phone}-{uuid.uuid4().hex[:8]}"

        meta = {
            "agent_id": campaign.agent_id,
            "client_id": campaign.client_id,
            "campaign_id": campaign.id,
            "lead_id": lead.id,
            "lead_name": lead.name or "",   # passed to agent for personalised greeting
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

            await livekit_service.dial_participant(
                room_name, dial_to, trunk_id, identity_number=phone
            )
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
        "skipped_missing_fields": skipped_missing,
        "errors": errors,
        "trunk_id": trunk_id,
    }
