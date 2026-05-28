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
    from livekit.agents.voice.turn import TurnHandlingOptions  # v1.5+ non-deprecated API
except ModuleNotFoundError:
    print(
        "\n[VBots] livekit-agents not installed in this venv.\n"
        "Run:\n"
        "  pip install livekit-agents==1.2.8 livekit-plugins-openai==1.2.8 "
        "livekit-plugins-sarvam==1.2.8 livekit-plugins-silero==1.2.8\n"
    )
    raise SystemExit(1)
from livekit.plugins import openai, sarvam, silero
try:
    from livekit.plugins import groq as groq_plugin
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

try:
    from livekit.plugins import deepgram as deepgram_plugin
    _DEEPGRAM_AVAILABLE = True
except ImportError:
    _DEEPGRAM_AVAILABLE = False

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
    # VAD detects SPEECH START/END boundaries (audio gating); EOU is decided by the LLM
    # semantic turn_detection when AGENT_TURN_DETECTION="semantic".
    # min_silence_duration=0.15 is the audio gate — a brief pause suspends audio to STT.
    # With semantic mode the LLM then decides whether it's a genuine end-of-turn, so
    # SIP background noise that causes a 0.15 s VAD gap will NOT trigger a false EOU.
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.15,
        prefix_padding_duration=0.15,
    )


class DynamicVoiceAgent(Agent):
    """Agent built from ai_agents row (prompt, voice, language, provider)."""

    def __init__(self, config, greeting: str):
        from app.db.models.ai_agent import AIProvider, Language
        from worker.config_loader import language_to_sarvam_code, voice_to_sarvam_speaker

        lang_code = language_to_sarvam_code(config.language)
        use_sarvam = config.provider == AIProvider.SARVAM

        deepgram_key = os.getenv("DEEPGRAM_API_KEY", "")
        if _DEEPGRAM_AVAILABLE and deepgram_key:
            # Streaming STT — processes audio while user speaks (stt_wait ≈ 0)
            # endpointing_ms=100: Deepgram sends is_final after 100ms silence (plugin default=25ms,
            #   but 25ms is too aggressive on SIP — causes mid-sentence finalization)
            # sample_rate=8000: must match PSTN/SIP 8kHz narrowband audio
            # no_delay=True: don't wait for smart_format sequences before emitting finals
            stt = deepgram_plugin.STT(
                model="nova",
                language="hi-Latn",   # Hinglish: Hindi in Latin/Roman script (code-switched)
                smart_format=True,
                punctuate=True,
                sample_rate=8000,
                endpointing_ms=100,
                no_delay=True,
            )
            logger.info("STT: Deepgram nova (streaming, hi-Latn Hinglish, 8kHz, endpointing=100ms)")
        elif use_sarvam:
            stt = sarvam.STT(
                language=lang_code,
                model=settings.AGENT_STT_MODEL,
                mode="transcribe",
                high_vad_sensitivity=False,
                sample_rate=settings.AGENT_AUDIO_SAMPLE_RATE,
                prompt=settings.AGENT_STT_PROMPT,
            )
            logger.info("STT: Sarvam %s (batch)", settings.AGENT_STT_MODEL)
        else:
            stt = openai.STT()
            logger.info("STT: OpenAI Whisper")

        reply_tokens = min(int(config.max_tokens), settings.AGENT_REPLY_MAX_TOKENS)
        phone_prompt = (
            f"{config.prompt}\n\n"
            "PHONE CALL RULES (strict):\n"
            "- Reply in MAX 1 sentence (10-15 words). Never longer.\n"
            "- Sound natural and warm, like a real person.\n"
            "- Ask only ONE question at a time.\n"
            "- No lists, no bullet points, no long explanations.\n"
            "- Use Hinglish naturally (mix Hindi + English words).\n"
            "- If you need a moment, say 'Hmm' or 'Achha' before replying."
        )
        groq_key = os.getenv("GROQ_API_KEY", "")
        if _GROQ_AVAILABLE and groq_key:
            llm = groq_plugin.LLM(
                model="llama-3.3-70b-versatile",
                temperature=float(config.temperature),
                max_completion_tokens=reply_tokens,
            )
            logger.info("LLM: Groq llama-3.3-70b-versatile (max_tokens=%d)", reply_tokens)
        else:
            llm = openai.LLM(
                model=config.model or settings.DEFAULT_LLM_MODEL,
                temperature=float(config.temperature),
                max_completion_tokens=reply_tokens,
            )
            logger.info(
                "LLM: OpenAI %s (max_tokens=%d) [groq_available=%s, groq_key=%s]",
                config.model or settings.DEFAULT_LLM_MODEL,
                reply_tokens,
                _GROQ_AVAILABLE,
                bool(groq_key),
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


async def finalize_call_log(room_name: str, *, failed: bool = False, callee_answered: bool = True) -> None:
    """Mark call completed/failed when LiveKit room ends."""
    try:
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.db.models.call_log import CallLog, CallStatus
        from app.db.models.campaign import Campaign, Lead, LeadStatus
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
            # Capture whether callee actually answered BEFORE changing status
            was_active = call.status == CallStatus.ACTIVE
            call.status = CallStatus.FAILED if failed else CallStatus.COMPLETED
            call.ended_at = now
            started = call.started_at
            if started:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                call.duration_seconds = max(0, int((now - started).total_seconds()))

            # ── Update lead status if this call was part of a campaign ──────────
            if call.lead_id:
                lead_result = await db.execute(select(Lead).where(Lead.id == call.lead_id))
                lead = lead_result.scalar_one_or_none()
                if lead and lead.status == LeadStatus.DIALING:
                    lead.last_called_at = now
                    # callee_answered=True only when wait_for_participant() succeeded (outbound)
                    # or always True for inbound (caller was already in room)
                    call_answered = callee_answered and not failed

                    if call_answered:
                        lead.status = LeadStatus.CONNECTED
                        logger.info("Lead %s → CONNECTED (call_id=%s duration=%ss)", lead.id, call.id, call.duration_seconds)
                    else:
                        lead.retry_count += 1
                        max_retries = 3
                        if lead.campaign_id:
                            camp_result = await db.execute(select(Campaign).where(Campaign.id == lead.campaign_id))
                            camp = camp_result.scalar_one_or_none()
                            if camp:
                                max_retries = camp.max_retries

                        if lead.retry_count >= max_retries:
                            lead.status = LeadStatus.NO_ANSWER if not failed else LeadStatus.FAILED
                            logger.info("Lead %s → %s (retries=%s/%s)", lead.id, lead.status, lead.retry_count, max_retries)
                        else:
                            lead.status = LeadStatus.NEW  # back to NEW for retry
                            logger.info("Lead %s → NEW for retry (attempt %s/%s)", lead.id, lead.retry_count, max_retries)

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
    # Inbound: caller is already in room → always answered
    # Outbound: only True after wait_for_participant() succeeds (callee picks up)
    callee_answered = {"value": not is_outbound_room}

    async def _on_call_end(_: str = "") -> None:
        await finalize_call_log(
            ctx.room.name,
            failed=session_failed["value"],
            callee_answered=callee_answered["value"],
        )

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

    # ── Turn detection ────────────────────────────────────────────────────────
    # Uses TurnHandlingOptions (v1.5+ non-deprecated API) to avoid the
    # deprecation-warning bundle and gain finer control.
    #
    # AGENT_TURN_DETECTION="stt"  (default / recommended for SIP):
    #   Deepgram sends is_final after endpointing_ms=100 ms of silence.
    #   That STT final triggers EOU — completely bypasses Silero VAD for
    #   end-of-turn decisions, so SIP background noise has no effect.
    #   Timeline: speech ends → Deepgram final (100 ms) → min_delay (300 ms)
    #             → agent responds.  Total: ~400 ms from last syllable.
    #
    # AGENT_TURN_DETECTION="vad":
    #   Falls back to Silero silence-threshold approach (sensitive to noise).
    #
    # VAD is still passed so it can gate audio-to-STT and handle interruptions.
    _turn_opts = TurnHandlingOptions(
        turn_detection=settings.AGENT_TURN_DETECTION,
        endpointing={
            "mode": "fixed",
            "min_delay": settings.AGENT_MIN_ENDPOINTING_DELAY,   # 0.30 s floor
            "max_delay": settings.AGENT_MAX_ENDPOINTING_DELAY,   # 1.5 s safety net
        },
        interruption={
            "enabled": config.interruptions_enabled,
            "min_duration": 0.35,
            "resume_false_interruption": True,
        },
        preemptive_generation={
            "enabled": settings.AGENT_PREEMPTIVE_GENERATION,
        },
    )
    session = AgentSession(
        vad=vad,
        turn_handling=_turn_opts,
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
            "Outbound: waiting for SIP participant to join room (expected_identity=%s, timeout=60s)",
            expected,
        )
        try:
            participant = await asyncio.wait_for(
                ctx.wait_for_participant(identity=expected) if expected else ctx.wait_for_participant(),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Outbound: callee did not join within 60s room=%s — phone may not have rung or was declined",
                room_name,
            )
            return

        sip_identity = participant.identity
        logger.info(
            "Outbound: SIP participant joined room identity=%s (checking answer status...)",
            sip_identity,
        )

        # ── Detect actual callee answer via sip.callStatus attribute ──────────────
        # LiveKit adds the SIP participant to the room the moment the outbound dial
        # is initiated (ringing phase), NOT when the callee picks up.
        # wait_for_participant() therefore returns immediately for every outbound room.
        # We must wait for participant attribute sip.callStatus == "active" which
        # LiveKit sets only after SIP 200 OK (callee answered).
        #
        # Fallback: if sip.callStatus is absent (older LiveKit), we assume answered
        # to preserve backward compatibility.
        # call_resolved fires on sip.callStatus == "active" (answered) OR "bye" (rejected/ended)
        # This lets us exit immediately instead of waiting the full 55 s timeout.
        call_resolved_event = asyncio.Event()
        sip_call_answered = {"value": False}

        def _check_sip_status(attrs: dict) -> None:
            status = attrs.get("sip.callStatus", "")
            if status:
                logger.info("Outbound: sip.callStatus=%r identity=%s", status, sip_identity)
            if status == "active":
                sip_call_answered["value"] = True
                call_resolved_event.set()
            elif status in ("bye", "disconnected"):
                call_resolved_event.set()  # ended without answer — exit immediately

        def _on_sip_attrs(changed_attrs: dict, p) -> None:
            if p.identity == sip_identity:
                merged = {**(dict(p.attributes) if p.attributes else {}), **changed_attrs}
                _check_sip_status(merged)

        # Register listener BEFORE reading current attrs (avoids race condition)
        ctx.room.on("participant_attributes_changed", _on_sip_attrs)

        current_attrs: dict = {}
        try:
            if hasattr(participant, "attributes") and participant.attributes:
                current_attrs = dict(participant.attributes)
        except Exception:
            pass
        logger.info("Outbound: initial participant attributes=%s", current_attrs)

        if "sip.callStatus" not in current_attrs:
            # Attributes may arrive asynchronously — wait up to 3 s for first delivery
            try:
                await asyncio.wait_for(call_resolved_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                pass  # no attributes yet; will re-check below

            if not call_resolved_event.is_set():
                # Re-fetch after brief wait
                try:
                    if hasattr(participant, "attributes") and participant.attributes:
                        current_attrs = dict(participant.attributes)
                except Exception:
                    pass

            if "sip.callStatus" not in current_attrs and not call_resolved_event.is_set():
                # Old LiveKit without SIP attribute support — fall back to original behavior
                logger.warning(
                    "Outbound: sip.callStatus attribute not present — assuming answered "
                    "(upgrade LiveKit SIP >= 1.7 for accurate answered detection)"
                )
                callee_answered["value"] = True
        else:
            _check_sip_status(current_attrs)

        if not call_resolved_event.is_set() and not callee_answered["value"]:
            # Wait for "active" or "bye" — exit as soon as either fires (max 55 s)
            try:
                await asyncio.wait_for(call_resolved_event.wait(), timeout=55.0)
            except asyncio.TimeoutError:
                logger.info(
                    "Outbound: callee did not answer (timeout, no sip.callStatus change) room=%s",
                    room_name,
                )
            finally:
                try:
                    ctx.room.off("participant_attributes_changed", _on_sip_attrs)
                except Exception:
                    pass

            if not sip_call_answered["value"]:
                # Not answered — shutdown callback will mark lead NO_ANSWER / retry
                return
        else:
            try:
                ctx.room.off("participant_attributes_changed", _on_sip_attrs)
            except Exception:
                pass

        if sip_call_answered["value"]:
            callee_answered["value"] = True
            logger.info(
                "Outbound: callee answered (sip.callStatus=active) identity=%s",
                sip_identity,
            )

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
