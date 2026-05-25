"""
VBots LiveKit Agent Worker (dynamic, per-DID via dispatch rules)

Run from backend/:
    python worker/agent.py dev

Requires .env with LIVEKIT_*, OPENAI_API_KEY, SARVAM_API_KEY, DATABASE_URL.

How routing works:
1. Inbound SIP hits a trunk/DID
2. LiveKit dispatch rule creates room agent-{agent_id}-xxx with metadata {"agent_id": N}
3. This worker receives the job, loads agent N from MySQL, runs STT/LLM/TTS
4. Different DIDs → different dispatch rules → different agent_id in metadata
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# backend/ on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

try:
    from livekit.agents import Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli
    from livekit.agents.voice import room_io
except ModuleNotFoundError:
    print(
        "\n[VBots] livekit-agents not installed in this venv.\n"
        "Run:\n"
        "  pip install livekit-agents==1.2.8 livekit-plugins-openai==1.2.8 "
        "livekit-plugins-sarvam==1.2.8 livekit-plugins-silero==1.2.8\n"
    )
    raise SystemExit(1)
from livekit.plugins import openai, sarvam, silero

from app.core.config import settings
from app.services.recording_service import recording_path_for_room
from worker.config_loader import (
    extract_caller_from_room_name,
    extract_did_from_metadata,
    load_agent_config,
    parse_metadata,
    resolve_agent_id,
)
from worker.call_tracking import attach_call_listeners
from worker.recordings import (
    persist_session_artifacts,
    session_record_options,
    should_record_call,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("vbots.agent")


def prewarm(proc: JobProcess) -> None:
    # Silero owns turn boundaries; Sarvam STT uses high_vad_sensitivity=False (see DynamicVoiceAgent)
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.42,
        prefix_padding_duration=0.35,
    )


class DynamicVoiceAgent(Agent):
    """Agent built from ai_agents row (prompt, voice, language, provider)."""

    def __init__(self, config, greeting: str):
        from app.db.models.ai_agent import AIProvider, Language
        from worker.config_loader import language_to_sarvam_code, voice_to_sarvam_speaker

        lang_code = language_to_sarvam_code(config.language)
        use_sarvam = config.provider == AIProvider.SARVAM

        stt = (
            sarvam.STT(
                language=lang_code,
                model=settings.AGENT_STT_MODEL,
                mode="transcribe",
                high_vad_sensitivity=False,
                sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                prompt=settings.AGENT_STT_PROMPT,
            )
            if use_sarvam
            else openai.STT()
        )

        reply_tokens = min(int(config.max_tokens), settings.AGENT_REPLY_MAX_TOKENS)
        phone_prompt = (
            f"{config.prompt}\n\n"
            "Phone call rules: reply in 1–2 short Hindi/Hinglish sentences only. "
            "No long lists. Ask one clarifying question at a time. "
            "If the caller asks for flights or tickets (e.g. Delhi to Mumbai), help with travel — "
            "do not assume property leasing unless they clearly ask for rent/lease."
        )
        llm = openai.LLM(
            model=config.model or settings.DEFAULT_LLM_MODEL,
            temperature=float(config.temperature),
            max_completion_tokens=reply_tokens,
        )

        tts = (
            sarvam.TTS(
                model=settings.AGENT_TTS_MODEL,
                speaker=voice_to_sarvam_speaker(
                    config.voice, tts_model=settings.AGENT_TTS_MODEL
                ),
                target_language_code=lang_code,
                speech_sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                enable_preprocessing=True,
                pace=1.05,
                temperature=0.45,
                pitch=0.04,
                loudness=1.02,
                max_chunk_length=120,
            )
            if use_sarvam
            else openai.TTS()
        )

        super().__init__(instructions=phone_prompt, stt=stt, llm=llm, tts=tts)
        self._greeting = greeting
        self._interruptions = config.interruptions_enabled

    async def on_enter(self):
        await self.session.say(self._greeting)


def _meta_int(meta: dict, key: str) -> int | None:
    val = meta.get(key)
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


async def create_call_log(
    ctx: JobContext,
    agent_id: int,
    caller: str | None,
    did_number: str | None = None,
    *,
    direction: str = "inbound",
    callee: str | None = None,
    campaign_id: int | None = None,
    lead_id: int | None = None,
) -> int | None:
    """Insert call_logs row and notify dashboard via WebSocket."""
    try:
        from datetime import datetime, timezone

        from app.db.models.call_log import CallDirection, CallLog, CallStatus
        from app.db.session import AsyncSessionLocal
        from app.websocket.manager import socket_manager
        from worker.config_loader import load_agent_config

        config = await load_agent_config(agent_id)
        if not config:
            return None
        is_outbound = direction == "outbound" or ctx.room.name.startswith("outbound-")
        call_direction = CallDirection.OUTBOUND if is_outbound else CallDirection.INBOUND

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            existing = await db.execute(
                select(CallLog)
                .where(CallLog.room_name == ctx.room.name)
                .order_by(CallLog.id.desc())
                .limit(1)
            )
            call = existing.scalar_one_or_none()
            if call:
                call.status = CallStatus.ACTIVE
                if campaign_id and not call.campaign_id:
                    call.campaign_id = campaign_id
                if lead_id and not call.lead_id:
                    call.lead_id = lead_id
                await db.commit()
                await db.refresh(call)
            else:
                call = CallLog(
                    client_id=config.client_id,
                    agent_id=agent_id,
                    campaign_id=campaign_id,
                    lead_id=lead_id,
                    room_name=ctx.room.name,
                    direction=call_direction,
                    status=CallStatus.ACTIVE,
                    caller_number=caller if not is_outbound else None,
                    callee_number=callee if is_outbound else None,
                    did_number=did_number,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(call)
                await db.commit()
                await db.refresh(call)
            await socket_manager.emit_call_update(
                config.client_id,
                {
                    "call_id": call.id,
                    "room_name": call.room_name,
                    "status": call.status.value,
                    "caller_number": caller,
                },
            )
            return call.id
    except Exception as e:
        logger.warning("Could not create call_log: %s", e)
        return None


async def finalize_call_log(room_name: str, *, failed: bool = False) -> None:
    """Mark call completed/failed when LiveKit room ends."""
    try:
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.db.models.call_log import CallLog, CallStatus
        from app.db.session import AsyncSessionLocal
        from app.websocket.manager import socket_manager
        from worker.call_tracking import refresh_call_sentiment_from_db

        call_id: int | None = None
        client_id: int | None = None
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallLog)
                .where(CallLog.room_name == room_name)
                .order_by(CallLog.id.desc())
                .limit(1)
            )
            call = result.scalar_one_or_none()
            if not call or call.status not in (CallStatus.ACTIVE, CallStatus.RINGING):
                return

            now = datetime.now(timezone.utc)
            call.status = CallStatus.FAILED if failed else CallStatus.COMPLETED
            call.ended_at = now
            started = call.started_at
            if started:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                call.duration_seconds = max(0, int((now - started).total_seconds()))
            await db.commit()

            call_id = call.id
            client_id = call.client_id

            await socket_manager.emit_call_update(
                client_id,
                {"call_id": call_id, "room_name": room_name, "status": call.status.value},
            )

        if call_id:
            await refresh_call_sentiment_from_db(call_id, client_id)
    except Exception as e:
        logger.warning("Could not finalize call_log for %s: %s", room_name, e)


async def entrypoint(ctx: JobContext):
    room_name = ctx.room.name
    logger.info(
        "Job started: room=%s | connecting to LiveKit %s (WebRTC UDP 50000-60000 must reach server)",
        room_name,
        settings.LIVEKIT_URL,
    )
    try:
        await ctx.connect()
    except Exception as e:
        logger.error(
            "Failed to connect to room %s: %s. "
            "Fix: set rtc.node_ip in LiveKit config to server LAN IP, open UDP 50000-60000, "
            "or run worker on LiveKit host with LIVEKIT_URL=ws://127.0.0.1:7880",
            room_name,
            e,
        )
        return
    logger.info("Connected to LiveKit room %s", room_name)

    room_meta = parse_metadata(getattr(ctx.room, "metadata", None))
    job_meta = parse_metadata(getattr(ctx.job, "metadata", None))

    from worker.config_loader import extract_callee_from_outbound_room

    is_outbound_room = room_name.startswith("outbound-")
    caller_number = (
        extract_callee_from_outbound_room(room_name)
        if is_outbound_room
        else extract_caller_from_room_name(room_name)
    )
    # Your business DID (number customers dial) — from metadata when LiveKit provides it
    did_number = extract_did_from_metadata(job_meta, room_meta)

    client_id = room_meta.get("client_id") or job_meta.get("client_id")
    trunk_id = job_meta.get("trunk_id") or room_meta.get("trunk_id") or job_meta.get("sip_trunk_id")

    agent_id = await resolve_agent_id(
        room_name=room_name,
        room_metadata=room_meta,
        job_metadata=job_meta,
        caller_number=caller_number,
        did_number=did_number,
        trunk_id=str(trunk_id) if trunk_id else None,
        client_id=int(client_id) if client_id else None,
        use_default_fallback=True,
    )

    if not agent_id:
        logger.error(
            "No agent_id for room=%s caller=%s did=%s — add AI agent or Dispatch rule (DID=your number, not customer)",
            room_name,
            caller_number,
            did_number,
        )
        return

    logger.info(
        "Call routing: agent_id=%s | caller(customer)=%s | did(your number)=%s | room=%s",
        agent_id,
        caller_number or "unknown",
        did_number or "not in metadata — using default/trunk agent",
        room_name,
    )

    call_id = await create_call_log(
        ctx,
        agent_id,
        caller_number,
        did_number,
        direction="outbound" if is_outbound_room else "inbound",
        callee=caller_number if is_outbound_room else None,
        campaign_id=_meta_int(room_meta, "campaign_id") or _meta_int(job_meta, "campaign_id"),
        lead_id=_meta_int(room_meta, "lead_id") or _meta_int(job_meta, "lead_id"),
    )

    session_failed = {"value": False}

    async def _on_call_end(_: str = "") -> None:
        await finalize_call_log(ctx.room.name, failed=session_failed["value"])

    ctx.add_shutdown_callback(_on_call_end)

    config = await load_agent_config(agent_id)
    if not config:
        logger.error("Agent %s not found or inactive in database", agent_id)
        return

    logger.info(
        "Starting agent id=%s name=%s room=%s language=%s voice=%s",
        config.id,
        config.name,
        ctx.room.name,
        config.language.value,
        config.voice,
    )

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load(
        min_silence_duration=0.42,
        prefix_padding_duration=0.35,
    )

    session = AgentSession(
        vad=vad,
        turn_detection="vad",
        allow_interruptions=config.interruptions_enabled,
        min_interruption_duration=0.35,
        min_endpointing_delay=settings.AGENT_MIN_ENDPOINTING_DELAY,
        max_endpointing_delay=settings.AGENT_MAX_ENDPOINTING_DELAY,
        min_consecutive_speech_delay=0.06,
        preemptive_generation=settings.AGENT_PREEMPTIVE_GENERATION,
        resume_false_interruption=True,
    )

    @session.on("error")
    def _on_session_error(_ev) -> None:
        session_failed["value"] = True

    @session.on("close")
    def _on_session_close(ev) -> None:
        if getattr(ev, "error", None):
            session_failed["value"] = True

    if call_id:
        attach_call_listeners(session, call_id, config.client_id)

    voice_agent = DynamicVoiceAgent(config, config.greeting)

    from app.services.phone_utils import sip_participant_identity

    sip_identity = None
    if is_outbound_room:
        expected = sip_participant_identity(caller_number) if caller_number else None
        logger.info(
            "Outbound: waiting for callee to answer (expected_identity=%s, timeout=60s)",
            expected,
        )
        try:
            participant = await asyncio.wait_for(
                ctx.wait_for_participant(identity=expected) if expected else ctx.wait_for_participant(),
                timeout=60.0,
            )
            sip_identity = participant.identity
            logger.info("Outbound: callee connected identity=%s", sip_identity)
        except asyncio.TimeoutError:
            logger.error(
                "Outbound: callee did not join within 60s room=%s — phone may not have rung or was declined",
                room_name,
            )
            return
    elif caller_number:
        sip_identity = sip_participant_identity(caller_number)
    telephony_hz = settings.AGENT_AUDIO_SAMPLE_RATE
    room_input = room_io.RoomInputOptions(
        participant_identity=sip_identity,
        close_on_disconnect=True,
        audio_sample_rate=telephony_hz,
        audio_num_channels=1,
    )
    room_output = room_io.RoomOutputOptions(
        sync_transcription=False,
        audio_sample_rate=telephony_hz,
        audio_num_channels=1,
    )

    record = session_record_options() if should_record_call(config.record_calls) else False

    await session.start(
        voice_agent,
        room=ctx.room,
        room_input_options=room_input,
        room_output_options=room_output,
        record=record,
    )

    if should_record_call(config.record_calls):

        async def _save_recording_on_shutdown(_: str = "") -> None:
            await persist_session_artifacts(ctx, session, call_id=call_id)

        ctx.add_shutdown_callback(_save_recording_on_shutdown)
        logger.info(
            "Session recording enabled; files saved under %s after each call",
            recording_path_for_room(ctx.room.name).parent,
        )


def _resolve_livekit_agent_name() -> str:
    """Read after load_dotenv; export to os.environ so dev watcher child processes inherit it."""
    name = (os.getenv("LIVEKIT_AGENT_NAME") or settings.LIVEKIT_AGENT_NAME or "vbots").strip()
    if not name:
        name = "vbots"
    os.environ["LIVEKIT_AGENT_NAME"] = name
    return name


if __name__ == "__main__":
    agent_name = _resolve_livekit_agent_name()
    logger.info(
        "VBots worker | LiveKit=%s | agent_name=%r | env_file=%s",
        settings.LIVEKIT_URL,
        agent_name,
        _ENV_PATH,
    )
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            ws_url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            agent_name=agent_name,
            # Windows: prefer start over dev (dev file-watcher is unstable)
            num_idle_processes=1,
        )
    )
