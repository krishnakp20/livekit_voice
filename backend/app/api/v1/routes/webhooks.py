import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.deps import DbSession
from app.services.vicidial_service import vicidial_service

router = APIRouter()
logger = logging.getLogger("vbots.webhooks")


@router.post("/livekit")
async def livekit_webhook(request: Request, db: DbSession):
    """Handle LiveKit room/participant/SIP events.

    Configure in LiveKit server yaml:
      webhook:
        urls:
          - http://api:8000/api/v1/webhooks/livekit
        api_key: APIvoicebot
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = body.get("event", "unknown")
    room = body.get("room") or {}
    participant = body.get("participant") or {}
    room_name = room.get("name", "")

    logger.debug("LiveKit event=%s room=%s", event, room_name)

    # SIP call ended before worker could clean up — mark call failed in DB
    if event == "room_finished" and room_name:
        try:
            from sqlalchemy import select
            from app.db.models.call_log import CallLog, CallStatus
            async with db as session:
                result = await session.execute(
                    select(CallLog)
                    .where(
                        CallLog.room_name == room_name,
                        CallLog.status.in_([CallStatus.RINGING, CallStatus.ACTIVE]),
                    )
                    .limit(1)
                )
                call = result.scalar_one_or_none()
                if call:
                    from datetime import datetime, timezone
                    call.status = CallStatus.COMPLETED
                    call.ended_at = datetime.now(timezone.utc)
                    if call.started_at:
                        started = call.started_at
                        if started.tzinfo is None:
                            started = started.replace(tzinfo=timezone.utc)
                        call.duration_seconds = max(
                            0, int((call.ended_at - started).total_seconds())
                        )
                    logger.info("room_finished webhook: closed call_log for room=%s", room_name)
        except Exception as e:
            logger.warning("room_finished webhook: could not update call_log: %s", e)

    if event == "participant_joined":
        logger.info(
            "participant_joined room=%s identity=%s",
            room_name,
            participant.get("identity", ""),
        )

    if event in ("sip_inbound_track_published", "sip_outbound_track_published"):
        logger.info("SIP media track event=%s room=%s", event, room_name)

    return {"status": "ok", "event": event}


@router.post("/vicidial/{client_id}")
async def vicidial_webhook(
    client_id: int,
    request: Request,
    db: DbSession,
    x_vicidial_signature: str = Header(default=""),
):
    body = await request.body()
    if settings.VICIDIAL_WEBHOOK_SECRET:
        if not vicidial_service.verify_webhook(body, x_vicidial_signature, settings.VICIDIAL_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    event = data.get("event", "unknown")
    result = await vicidial_service.handle_webhook(db, client_id, event, data)
    return result
