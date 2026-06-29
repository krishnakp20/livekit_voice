"""Persist agent sessions recordings (LiveKit Agents built-in session recording).

Uses AgentSession.start(record=...) — same approach as the working vbot script.
Does NOT wrap audio after start (that breaks SIP) and does NOT require LiveKit Egress.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livekit.agents import AgentSession
from livekit.agents.job import JobContext
from livekit.agents.voice.agent_session import RecordingOptions

from app.services.recording_service import recording_path_for_room, upsert_recording

logger = logging.getLogger("vbots.recordings")


def recording_enabled() -> bool:
    return os.getenv("VBOT_RECORDING_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def should_record_call(record_calls: bool) -> bool:
    return bool(record_calls) and recording_enabled()


def session_record_options() -> RecordingOptions:
    """Built-in session recorder: audio + transcript; skip heavy OTLP on self-hosted."""
    return {
        "audio": True,
        "transcript": True,
        "traces": False,
        "logs": False,
    }


async def persist_session_artifacts(
    ctx: JobContext,
    session: AgentSession,
    *,
    call_id: int | None = None,
) -> None:
    """Copy session audio.ogg into RECORDINGS_PATH and register in DB."""
    if not recording_enabled():
        return

    room_name = ctx.room.name
    dest = recording_path_for_room(room_name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    src_audio = ctx.session_directory / "audio.ogg"
    if src_audio.is_file():
        shutil.copy2(src_audio, dest)
        logger.info("Call recording saved room=%s path=%s", room_name, dest)
    else:
        logger.warning(
            "No audio.ogg in session directory %s (was record=True on session.start?)",
            ctx.session_directory,
        )
        return

    if not call_id:
        from sqlalchemy import select

        from app.db.models.call_log import CallLog
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallLog)
                .where(CallLog.room_name == room_name)
                .order_by(CallLog.id.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            call_id = row.id if row else None

    if not call_id:
        return

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await upsert_recording(db, call_id=call_id, file_path=dest)
    logger.info("Recording registered call_id=%s", call_id)

    try:
        report = ctx.make_session_report(session)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_room = "".join(c if c.isalnum() or c in "-_" else "_" for c in room_name)[:80]
        report_path = dest.parent / f"{safe_room}_{ctx.job.id}_{ts}_report.json"
        report_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug("Session report saved: %s", report_path)
    except Exception:
        logger.debug("Session report not written", exc_info=True)
