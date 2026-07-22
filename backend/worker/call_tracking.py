"""Persist call transcripts and log per-turn latency breakdown (STT / LLM / TTS)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from livekit.agents.metrics.base import EOUMetrics, LLMMetrics, STTMetrics, TTSMetrics
from livekit.agents.voice.events import ConversationItemAddedEvent, MetricsCollectedEvent, UserInputTranscribedEvent

if TYPE_CHECKING:
    from livekit.agents import AgentSession

logger = logging.getLogger("vbots.call_tracking")


@dataclass
class _CallUsage:
    """Cumulative usage for an entire call — summed across all turns."""

    stt_audio_s: float = 0.0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    tts_chars: int = 0


# Per-call usage accumulators, keyed by call_id (lives in worker process memory).
_USAGE: dict[int, _CallUsage] = {}


async def persist_call_costs(call_id: int) -> None:
    """Compute STT/LLM/TTS cost from accumulated usage and save to call_logs.

    Called once at call end. Pops the accumulator so memory is freed.
    """
    usage = _USAGE.pop(call_id, None)
    if usage is None:
        return

    from sqlalchemy import select

    from app.core.config import settings
    from app.db.models.call_log import CallLog
    from app.db.session import AsyncSessionLocal

    stt_cost = (usage.stt_audio_s / 60.0) * settings.COST_STT_PER_MINUTE
    llm_cost = (
        usage.llm_prompt_tokens / 1_000_000 * settings.COST_LLM_INPUT_PER_1M
        + usage.llm_completion_tokens / 1_000_000 * settings.COST_LLM_OUTPUT_PER_1M
    )
    tts_cost = usage.tts_chars / 1_000_000 * settings.COST_TTS_PER_1M_CHARS
    total_cost = stt_cost + llm_cost + tts_cost

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(CallLog).where(CallLog.id == call_id))
            call = result.scalar_one_or_none()
            if call:
                call.stt_audio_seconds = round(usage.stt_audio_s, 2)
                call.llm_prompt_tokens = usage.llm_prompt_tokens
                call.llm_completion_tokens = usage.llm_completion_tokens
                call.tts_characters = usage.tts_chars
                call.stt_cost = round(stt_cost, 6)
                call.llm_cost = round(llm_cost, 6)
                call.tts_cost = round(tts_cost, 6)
                call.total_cost = round(total_cost, 6)
                await db.commit()
        logger.info(
            "COST call_id=%s | stt=$%.5f (%.1fs) | llm=$%.5f (%d in/%d out) | "
            "tts=$%.5f (%d chars) | total=$%.5f",
            call_id,
            stt_cost,
            usage.stt_audio_s,
            llm_cost,
            usage.llm_prompt_tokens,
            usage.llm_completion_tokens,
            tts_cost,
            usage.tts_chars,
            total_cost,
        )
    except Exception as e:
        logger.warning("Could not persist call costs call_id=%s: %s", call_id, e)


@dataclass
class _TurnBucket:
    """Metrics for one user→agent turn."""

    user_text: str = ""
    stt_audio_s: float = 0.0
    stt_api_s: float = 0.0
    eou_s: float = 0.0
    transcription_s: float = 0.0
    llm_ttft_s: float = 0.0
    llm_total_s: float = 0.0
    tts_ttfb_s: float = 0.0
    tts_play_s: float = 0.0
    _tts_chunks: int = 0
    turn_started: float = field(default_factory=time.monotonic)

    def record_tts(self, ttfb: float, audio: float) -> None:
        if self._tts_chunks == 0:
            self.tts_ttfb_s = ttfb
        self.tts_play_s += audio
        self._tts_chunks += 1

    def log_breakdown(self, call_id: int, turn_no: int) -> None:
        """Single-line latency summary after each agent reply."""
        after_user_stops = (
            self.stt_api_s + self.transcription_s + self.llm_total_s + self.tts_ttfb_s
        )
        total_wall = time.monotonic() - self.turn_started
        logger.info(
            "LATENCY BREAKDOWN call_id=%s turn=%s | "
            "user_speaking=%.2fs | stt_api=%.2fs | vad/eou=%.2fs | stt_wait=%.2fs | "
            "llm_ttft=%.2fs llm_total=%.2fs | tts_ttfb=%.2fs tts_play=%.2fs | "
            "after_you_stop≈%.2fs | wall=%.2fs | user=%r",
            call_id,
            turn_no,
            self.stt_audio_s,
            self.stt_api_s,
            self.eou_s,
            self.transcription_s,
            self.llm_ttft_s,
            self.llm_total_s,
            self.tts_ttfb_s,
            self.tts_play_s,
            after_user_stops,
            total_wall,
            (self.user_text[:60] + "…") if len(self.user_text) > 60 else self.user_text,
        )


async def _update_call_sentiment(call_id: int, client_id: int, caller_lines: list[str]) -> float | None:
    """Score from full caller transcript so far (not the last line alone)."""
    from sqlalchemy import select

    from app.db.models.call_log import CallLog
    from app.db.session import AsyncSessionLocal
    from app.services.ai_service import ai_service
    from app.websocket.manager import socket_manager

    combined = "\n".join(line.strip() for line in caller_lines if line.strip())
    if not combined:
        return None
    try:
        score = await ai_service.analyze_call_sentiment(combined)
    except Exception as e:
        logger.warning("Sentiment analysis failed call_id=%s: %s", call_id, e)
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CallLog).where(CallLog.id == call_id))
        call = result.scalar_one_or_none()
        if call:
            call.sentiment_score = score
            await db.commit()

    await socket_manager.emit_sentiment(client_id, call_id, score)
    logger.info("Call sentiment call_id=%s score=%.2f", call_id, score)
    return score


_PHONE_KEY_RE = re.compile(r"phone|mobile|contact.*no|calling.*no", re.IGNORECASE)


def _overwrite_phone_fields_with_caller_id(data: dict, fields: list, call) -> None:
    """Replace any phone-like extracted field with the actual SIP caller/callee number.

    The LLM extracts phone numbers by parsing spoken digits from the transcript
    ("double nine double one...") which is unreliable and pointless — the real
    number is already known from the SIP call itself. Whichever field name the
    client's CRM uses (Calling Phone no., Contact Number, Mobile, ...), if its
    normalised key looks like a phone field, overwrite it with the true number."""
    raw = call.caller_number if call.direction.value == "inbound" else call.callee_number
    if not raw:
        return
    digits = re.sub(r"\D", "", raw).lstrip("0")
    # Store as a plain 10-digit Indian mobile (matches what the CRM/template expects).
    real_phone = digits[-10:] if len(digits) >= 10 else digits
    if not real_phone:
        return

    for f in fields:
        key = f.get("key")
        if key and _PHONE_KEY_RE.search(key):
            data[key] = real_phone


async def extract_and_store_call_data(call_id: int) -> None:
    """At call end: extract the agent's configured fields from the transcript → JSON.

    No-op if the agent has no data_fields_json configured.
    """
    import json as _json

    from sqlalchemy import select

    from app.db.models.ai_agent import AIAgent
    from app.db.models.call_log import CallLog
    from app.db.models.transcript import SpeakerRole, Transcript
    from app.db.session import AsyncSessionLocal
    from app.services.ai_service import ai_service

    async with AsyncSessionLocal() as db:
        call = (
            await db.execute(select(CallLog).where(CallLog.id == call_id))
        ).scalar_one_or_none()
        if not call or not call.agent_id:
            return
        agent = (
            await db.execute(select(AIAgent).where(AIAgent.id == call.agent_id))
        ).scalar_one_or_none()
        if not agent or not agent.data_fields_json:
            return
        try:
            fields = _json.loads(agent.data_fields_json)
        except (ValueError, TypeError):
            return
        if not isinstance(fields, list) or not fields:
            return

        # Build the full transcript (both speakers) in order.
        rows = await db.execute(
            select(Transcript.speaker, Transcript.content)
            .where(Transcript.call_id == call_id)
            .order_by(Transcript.sequence)
        )
        lines = []
        for speaker, content in rows.all():
            if not content:
                continue
            who = "Customer" if speaker == SpeakerRole.USER else "Agent"
            lines.append(f"{who}: {content}")
        transcript = "\n".join(lines)
        if not transcript:
            return

        data = await ai_service.extract_call_data(transcript, fields)
        if data:
            _overwrite_phone_fields_with_caller_id(data, fields, call)
            call.collected_data = _json.dumps(data, ensure_ascii=False)
            await db.commit()
            logger.info("Collected data call_id=%s: %s", call_id, data)

            # Push to the client's CRM webhook (no-op when the agent has none).
            # Wrapped so a CRM outage can never break call teardown.
            try:
                from worker.crm_webhook import send_call_webhook

                await send_call_webhook(agent, data, call_id)
            except Exception as e:
                logger.warning("CRM webhook dispatch failed call_id=%s: %s", call_id, e)


async def refresh_call_sentiment_from_db(call_id: int, client_id: int) -> None:
    """Re-score at hangup from all saved user transcript lines."""
    from sqlalchemy import select

    from app.db.models.transcript import SpeakerRole, Transcript
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Transcript.content)
            .where(Transcript.call_id == call_id, Transcript.speaker == SpeakerRole.USER)
            .order_by(Transcript.sequence)
        )
        lines = [row for row in result.scalars().all() if row]
    if lines:
        await _update_call_sentiment(call_id, client_id, lines)


async def _save_transcript(
    call_id: int,
    client_id: int,
    *,
    speaker: str,
    content: str,
    llm_response: str | None = None,
    latency_ms: int | None = None,
    sentiment: float | None = None,
) -> None:
    from sqlalchemy import func, select

    from app.db.models.transcript import SpeakerRole, Transcript
    from app.db.session import AsyncSessionLocal
    from app.websocket.manager import socket_manager

    role = SpeakerRole.USER if speaker == "user" else SpeakerRole.AGENT
    async with AsyncSessionLocal() as db:
        seq_result = await db.execute(
            select(func.coalesce(func.max(Transcript.sequence), 0)).where(Transcript.call_id == call_id)
        )
        seq = int(seq_result.scalar_one()) + 1
        row = Transcript(
            call_id=call_id,
            speaker=role,
            content=content,
            llm_response=llm_response,
            latency_ms=latency_ms,
            sentiment=sentiment,
            sequence=seq,
        )
        db.add(row)
        await db.commit()

    await socket_manager.emit_transcript(
        client_id,
        call_id,
        {"speaker": speaker, "content": content, "response": llm_response},
    )


def attach_call_listeners(session: AgentSession, call_id: int, client_id: int) -> None:
    """Wire AgentSession events → MySQL transcripts + per-turn latency breakdown."""
    turn_no = {"n": 0}
    bucket: dict[str, _TurnBucket | None] = {"current": None}
    caller_lines: list[str] = []
    usage = _USAGE.setdefault(call_id, _CallUsage())

    def _new_turn(user_text: str = "") -> _TurnBucket:
        b = _TurnBucket(user_text=user_text)
        bucket["current"] = b
        return b

    @session.on("metrics_collected")
    def on_metrics(ev: MetricsCollectedEvent) -> None:
        m = ev.metrics
        b = bucket["current"]
        if b is None and not isinstance(m, (STTMetrics, EOUMetrics)):
            return

        if isinstance(m, STTMetrics):
            if b is None:
                b = _new_turn()
            if m.audio_duration > 0:
                b.stt_audio_s = max(b.stt_audio_s, m.audio_duration)
                usage.stt_audio_s += m.audio_duration
            if m.duration > 0:
                b.stt_api_s = max(b.stt_api_s, m.duration)
        elif isinstance(m, EOUMetrics):
            if b is None:
                b = _new_turn()
            b.eou_s = max(b.eou_s, m.end_of_utterance_delay)
            b.transcription_s = max(b.transcription_s, m.transcription_delay)
        elif isinstance(m, LLMMetrics) and m.completion_tokens > 0:
            if b is None:
                b = _new_turn()
            if m.ttft >= 0:
                b.llm_ttft_s = m.ttft
            b.llm_total_s = max(b.llm_total_s, m.duration)
            usage.llm_prompt_tokens += int(getattr(m, "prompt_tokens", 0) or 0)
            usage.llm_completion_tokens += int(getattr(m, "completion_tokens", 0) or 0)
        elif isinstance(m, TTSMetrics):
            if b is None:
                b = _new_turn()
            b.record_tts(m.ttfb, m.audio_duration)
            usage.tts_chars += int(getattr(m, "characters_count", 0) or 0)

    @session.on("user_input_transcribed")
    def on_user_transcribed(ev: UserInputTranscribedEvent) -> None:
        if not ev.is_final or not (ev.transcript or "").strip():
            return
        text = ev.transcript.strip()
        if bucket["current"] is None:
            _new_turn(text)
        else:
            bucket["current"].user_text = text
        logger.info("User said (call_id=%s): %s", call_id, text[:120])

    @session.on("conversation_item_added")
    def on_conversation_item(ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if getattr(item, "type", None) != "message":
            return
        text = getattr(item, "text_content", None)
        if not text or not str(text).strip():
            return
        role = getattr(item, "role", "")
        content = str(text).strip()

        import asyncio

        if role == "user":
            if bucket["current"] is None:
                _new_turn(content)
            else:
                bucket["current"].user_text = content

            async def _save_user_turn() -> None:
                caller_lines.append(content)
                await _update_call_sentiment(call_id, client_id, caller_lines)
                await _save_transcript(
                    call_id,
                    client_id,
                    speaker="user",
                    content=content,
                )

            asyncio.create_task(_save_user_turn())
        elif role == "assistant":
            b = bucket["current"] or _new_turn()
            turn_no["n"] += 1
            b.log_breakdown(call_id, turn_no["n"])
            bucket["current"] = None
            asyncio.create_task(
                _save_transcript(
                    call_id,
                    client_id,
                    speaker="agent",
                    content=content,
                    llm_response=content,
                )
            )
            logger.info("Agent replied (call_id=%s): %s", call_id, content[:120])
