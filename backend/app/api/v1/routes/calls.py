import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.db.models.ai_agent import AIAgent
from app.db.models.call_log import CallDirection, CallLog, CallStatus
from app.db.models.sip_trunk import SIPTrunk, TrunkDirection
from app.db.models.transcript import Transcript
from app.schemas.call import CallLogResponse, LiveCallResponse
from app.schemas.recording import RecordingResponse
from app.services.campaign_dial_service import get_outbound_livekit_trunk_id
from app.services.phone_utils import format_phone_for_sip
from app.services.call_cleanup_service import reconcile_stale_live_calls
from app.services.livekit_service import livekit_service

logger = logging.getLogger("vbots.calls")
from app.services.recording_service import (
    get_recording_for_call,
    recording_api_url,
    resolve_recording_path,
    upsert_recording,
)

router = APIRouter()


async def _enrich_call_response(db: DbSession, call: CallLog) -> CallLogResponse:
    response = CallLogResponse.model_validate(call)
    rec = await get_recording_for_call(db, call.id)
    stored = rec.file_path if rec else None
    disk = resolve_recording_path(call.room_name, stored)
    if disk:
        response.has_recording = True
        response.recording_url = rec.file_url if rec else recording_api_url(call.id)
        if not rec:
            await upsert_recording(
                db, call_id=call.id, file_path=disk, duration_seconds=call.duration_seconds
            )
    return response


@router.get("", response_model=list[CallLogResponse])
async def list_calls(db: DbSession, current_user: CurrentUser, skip: int = 0, limit: int = 50):
    result = await db.execute(
        select(CallLog)
        .where(CallLog.client_id == current_user.client_id)
        .order_by(CallLog.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    calls = result.scalars().all()
    return [await _enrich_call_response(db, c) for c in calls]


@router.get("/export.csv")
async def export_calls_csv(
    db: DbSession,
    current_user: CurrentUser,
    campaign_id: Optional[int] = None,
):
    """Download all calls as CSV, including every collected_data field as its own column."""
    import csv
    import io
    import json as _json

    from fastapi.responses import StreamingResponse

    query = select(CallLog).where(CallLog.client_id == current_user.client_id)
    if campaign_id is not None:
        query = query.where(CallLog.campaign_id == campaign_id)
    result = await db.execute(query.order_by(CallLog.started_at.desc()))
    calls = result.scalars().all()

    # Parse collected_data for each call and gather the union of all field keys.
    parsed: list[dict] = []
    data_keys: list[str] = []
    for c in calls:
        d = {}
        if c.collected_data:
            try:
                d = _json.loads(c.collected_data) or {}
            except (ValueError, TypeError):
                d = {}
        for k in d:
            if k not in data_keys:
                data_keys.append(k)
        parsed.append(d)

    base_cols = [
        "id", "direction", "status", "caller_number", "callee_number", "did_number",
        "duration_seconds", "sentiment_score", "disposition",
        "stt_cost", "llm_cost", "tts_cost", "total_cost",
        "started_at", "ended_at",
    ]
    header = base_cols + [f"data_{k}" for k in data_keys]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for c, d in zip(calls, parsed):
        row = [
            c.id,
            c.direction.value if c.direction else "",
            c.status.value if c.status else "",
            c.caller_number or "",
            c.callee_number or "",
            c.did_number or "",
            c.duration_seconds if c.duration_seconds is not None else "",
            f"{c.sentiment_score:.2f}" if c.sentiment_score is not None else "",
            c.disposition or "",
            f"{c.stt_cost or 0:.6f}",
            f"{c.llm_cost or 0:.6f}",
            f"{c.tts_cost or 0:.6f}",
            f"{c.total_cost or 0:.6f}",
            c.started_at.isoformat() if c.started_at else "",
            c.ended_at.isoformat() if c.ended_at else "",
        ]
        row += [("" if d.get(k) is None else str(d.get(k))) for k in data_keys]
        writer.writerow(row)

    buf.seek(0)
    filename = f"calls_export{'_campaign_' + str(campaign_id) if campaign_id else ''}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/live/reconcile")
async def reconcile_live_calls(db: DbSession, current_user: CurrentUser):
    """Close stale ringing/active rows (ghost dashboard live count)."""
    n = await reconcile_stale_live_calls(db, current_user.client_id)
    return {"closed": n}


@router.get("/live", response_model=list[LiveCallResponse])
async def live_calls(db: DbSession, current_user: CurrentUser):
    await reconcile_stale_live_calls(db, current_user.client_id)
    result = await db.execute(
        select(CallLog).where(
            CallLog.client_id == current_user.client_id,
            CallLog.status.in_([CallStatus.RINGING, CallStatus.ACTIVE]),
            CallLog.ended_at.is_(None),
        )
    )
    calls = result.scalars().all()
    live = []
    for call in calls:
        agent_name = "Unknown"
        if call.agent_id:
            agent_result = await db.execute(select(AIAgent).where(AIAgent.id == call.agent_id))
            agent = agent_result.scalar_one_or_none()
            if agent:
                agent_name = agent.name

        duration = 0
        if call.started_at:
            started = call.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            duration = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))

        transcript_result = await db.execute(
            select(Transcript)
            .where(Transcript.call_id == call.id)
            .order_by(Transcript.sequence.desc())
            .limit(1)
        )
        latest = transcript_result.scalar_one_or_none()

        display_number = call.caller_number or call.callee_number
        live.append(
            LiveCallResponse(
                call_id=call.id,
                room_name=call.room_name,
                agent_name=agent_name,
                caller_number=display_number,
                duration_seconds=duration,
                status=call.status,
                agent_speaking=False,
                user_speaking=False,
                latest_transcript=latest.content if latest else None,
                sentiment_score=call.sentiment_score,
            )
        )
    return live


@router.get("/{call_id}", response_model=CallLogResponse)
async def get_call(call_id: int, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(CallLog).where(CallLog.id == call_id, CallLog.client_id == current_user.client_id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    transcript_result = await db.execute(
        select(Transcript).where(Transcript.call_id == call_id).order_by(Transcript.sequence)
    )
    transcripts = transcript_result.scalars().all()
    response = await _enrich_call_response(db, call)
    response.transcripts = transcripts
    return response


@router.get("/{call_id}/recording", response_model=RecordingResponse)
async def get_call_recording_meta(call_id: int, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(CallLog).where(CallLog.id == call_id, CallLog.client_id == current_user.client_id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    rec = await get_recording_for_call(db, call_id)
    path = resolve_recording_path(call.room_name, rec.file_path if rec else None)
    has_file = path is not None
    if has_file and not rec:
        rec = await upsert_recording(
            db, call_id=call_id, file_path=path, duration_seconds=call.duration_seconds
        )

    return RecordingResponse(
        call_id=call_id,
        has_recording=has_file,
        recording_url=recording_api_url(call_id) if has_file else None,
        duration_seconds=rec.duration_seconds if rec else call.duration_seconds,
        size_bytes=rec.size_bytes if rec else (path.stat().st_size if has_file else None),
        format=rec.format if rec else "ogg",
    )


@router.get("/{call_id}/recording/file")
async def stream_call_recording(call_id: int, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(CallLog).where(CallLog.id == call_id, CallLog.client_id == current_user.client_id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    rec = await get_recording_for_call(db, call_id)
    path = resolve_recording_path(call.room_name, rec.file_path if rec else None)
    if not path:
        raise HTTPException(status_code=404, detail="Recording not available for this call")

    return FileResponse(
        path,
        media_type="audio/ogg",
        filename=f"call-{call_id}.ogg",
        headers={"Accept-Ranges": "bytes"},
    )


@router.post("/outbound")
async def initiate_outbound(
    db: DbSession,
    current_user: CurrentUser,
    agent_id: int,
    phone: str,
    trunk_id: Optional[int] = None,
):
    """
    Place one outbound call. ``trunk_id`` is the **SIP Trunks** row id in VBots (e.g. 5),
    not the LiveKit id (e.g. ST_xxx). Omit to use the client's active outbound trunk.
    """
    agent_result = await db.execute(
        select(AIAgent).where(AIAgent.id == agent_id, AIAgent.client_id == current_user.client_id)
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.is_active:
        raise HTTPException(status_code=400, detail="Agent is inactive — activate it in AI Agents first")

    if trunk_id is not None:
        trunk_result = await db.execute(
            select(SIPTrunk).where(
                SIPTrunk.id == trunk_id,
                SIPTrunk.client_id == current_user.client_id,
            )
        )
        trunk = trunk_result.scalar_one_or_none()
        if not trunk:
            raise HTTPException(status_code=404, detail="SIP trunk not found")
        if trunk.direction != TrunkDirection.OUTBOUND:
            raise HTTPException(status_code=400, detail="trunk_id must be an outbound SIP trunk")
        if not trunk.livekit_trunk_id:
            raise HTTPException(
                status_code=400,
                detail="Trunk has no LiveKit id — sync SIP Trunks from LiveKit first",
            )
        lk_trunk_id = trunk.livekit_trunk_id
    else:
        try:
            lk_trunk_id = await get_outbound_livekit_trunk_id(db, current_user.client_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    sip_phone = format_phone_for_sip(phone)
    safe_phone = re.sub(r"\D", "", sip_phone)
    if len(safe_phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    meta = {"agent_id": agent_id, "client_id": current_user.client_id, "direction": "outbound"}
    room_name = f"outbound-{agent_id}-{safe_phone}-{uuid.uuid4().hex[:8]}"

    try:
        await livekit_service.create_room_with_agent(room_name, meta)
    except Exception as e:
        logger.exception("create_room_with_agent failed room=%s", room_name)
        raise HTTPException(status_code=502, detail=f"LiveKit room failed: {e}") from e

    call = CallLog(
        client_id=current_user.client_id,
        agent_id=agent_id,
        room_name=room_name,
        callee_number=safe_phone,
        direction=CallDirection.OUTBOUND,
        status=CallStatus.RINGING,
    )
    db.add(call)
    await db.flush()

    try:
        await livekit_service.dial_participant(room_name, sip_phone, lk_trunk_id)
        # Stay ringing until worker marks active when callee answers; finalize on hangup
    except Exception as e:
        call.status = CallStatus.FAILED
        logger.exception(
            "outbound dial failed room=%s phone=%s lk_trunk=%s",
            room_name,
            sip_phone,
            lk_trunk_id,
        )
        await db.refresh(call)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "SIP outbound dial failed",
                "error": str(e),
                "call_id": call.id,
                "room_name": room_name,
                "livekit_trunk_id": lk_trunk_id,
                "phone_dialed": sip_phone,
            },
        ) from e

    await db.refresh(call)
    return {
        "call_id": call.id,
        "room_name": room_name,
        "status": call.status.value,
        "livekit_trunk_id": lk_trunk_id,
        "phone_dialed": sip_phone,
    }
