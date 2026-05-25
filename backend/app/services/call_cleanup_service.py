"""Close call_logs left in ringing/active after the real call has ended."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from livekit import api
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.call_log import CallLog, CallStatus
from app.services.livekit_service import livekit_service

logger = logging.getLogger("vbots.call_cleanup")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _livekit_room_names() -> Optional[set[str]]:
    """Return set of room names, or None if LiveKit list failed."""
    try:
        resp = await livekit_service.lkapi.room.list_rooms(api.ListRoomsRequest())
        return {r.name for r in resp.rooms}
    except Exception as e:
        logger.warning("Could not list LiveKit rooms for stale call cleanup: %s", e)
        return None


async def reconcile_stale_live_calls(db: AsyncSession, client_id: int) -> int:
    """
    Mark ringing/active rows as ended when the LiveKit room is gone or the call is stale.
    Returns number of rows updated.
    """
    now = _utc_now()
    ringing_cutoff = now - timedelta(seconds=settings.LIVE_CALL_RINGING_MAX_SECONDS)
    active_cutoff = now - timedelta(seconds=settings.LIVE_CALL_ACTIVE_MAX_SECONDS)
    orphan_cutoff = now - timedelta(seconds=settings.LIVE_CALL_ORPHAN_SECONDS)
    ringing_grace = timedelta(seconds=45)

    result = await db.execute(
        select(CallLog).where(
            CallLog.client_id == client_id,
            CallLog.status.in_([CallStatus.RINGING, CallStatus.ACTIVE]),
            CallLog.ended_at.is_(None),
        )
    )
    calls = result.scalars().all()
    if not calls:
        return 0

    live_rooms = await _livekit_room_names()
    closed = 0

    for call in calls:
        started = _as_utc(call.started_at) if call.started_at else now
        age = now - started
        in_livekit = live_rooms is not None and call.room_name in live_rooms

        # Orphan: room may exist but worker never connected / call already ended on phone
        if started < orphan_cutoff:
            if in_livekit:
                try:
                    await livekit_service.delete_room(call.room_name)
                except Exception as e:
                    logger.debug("delete_room %s: %s", call.room_name, e)
            call.status = CallStatus.MISSED if call.status == CallStatus.RINGING else CallStatus.COMPLETED
            call.ended_at = now
            call.duration_seconds = 0 if call.status == CallStatus.MISSED else max(0, int(age.total_seconds()))
            closed += 1
            logger.info(
                "Closed orphan call id=%s room=%s (age %ss)",
                call.id,
                call.room_name,
                int(age.total_seconds()),
            )
            continue

        if live_rooms is not None and not in_livekit:
            if call.status == CallStatus.RINGING and age < ringing_grace:
                continue
            call.status = CallStatus.MISSED if call.status == CallStatus.RINGING else CallStatus.COMPLETED
            call.ended_at = now
            call.duration_seconds = 0 if call.status == CallStatus.MISSED else max(0, int(age.total_seconds()))
            closed += 1
            logger.info("Closed ghost call id=%s room=%s (no LiveKit room)", call.id, call.room_name)
            continue

        if call.status == CallStatus.RINGING and started < ringing_cutoff:
            call.status = CallStatus.MISSED
            call.ended_at = now
            call.duration_seconds = 0
            closed += 1
        elif call.status == CallStatus.ACTIVE and started < active_cutoff:
            call.status = CallStatus.COMPLETED
            call.ended_at = now
            call.duration_seconds = max(0, int(age.total_seconds()))
            closed += 1

    if closed:
        await db.flush()
    return closed
