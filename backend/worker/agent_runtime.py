"""
Dynamic AI Agent Runtime Worker

Single worker process handles all agents dynamically.
Agent config loaded from DB per call.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.ai_agent import AIAgent
from app.db.models.call_log import CallLog, CallStatus
from app.db.models.transcript import SpeakerRole, Transcript
from app.services.ai_service import ai_service
from app.websocket.manager import socket_manager

logger = logging.getLogger("vbots.worker")
logging.basicConfig(level=logging.INFO)

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class AgentSession:
    """Per-call agent session with dynamic config."""

    def __init__(self, agent: AIAgent, call_id: int, client_id: int, room_name: str):
        self.agent = agent
        self.call_id = call_id
        self.client_id = client_id
        self.room_name = room_name
        self.conversation_history: list[dict] = []
        self.sequence = 0
        self.agent_speaking = False
        self.user_speaking = False
        self.silence_timer: Optional[asyncio.Task] = None

    async def on_user_speech(self, text: str, db: AsyncSession) -> str:
        self.user_speaking = True
        self.agent_speaking = False

        response, latency_ms = await ai_service.generate_response(
            self.agent, text, self.conversation_history
        )

        self.conversation_history.append({"role": "user", "content": text})
        self.conversation_history.append({"role": "assistant", "content": response})

        sentiment = await ai_service.analyze_sentiment(text)

        self.sequence += 1
        transcript = Transcript(
            call_id=self.call_id,
            speaker=SpeakerRole.USER,
            content=text,
            llm_response=response,
            latency_ms=latency_ms,
            sentiment=sentiment,
            sequence=self.sequence,
        )
        db.add(transcript)
        await db.flush()

        await socket_manager.emit_transcript(
            self.client_id,
            self.call_id,
            {"speaker": "user", "content": text, "response": response},
        )
        await socket_manager.emit_sentiment(self.client_id, self.call_id, sentiment)

        self.user_speaking = False
        self.agent_speaking = True
        return response

    async def get_greeting(self) -> str:
        return self.agent.greeting

    async def on_silence_timeout(self, db: AsyncSession) -> str:
        return self.agent.fallback_message


class AgentRuntimeWorker:
    """
    Single worker managing multiple concurrent agent sessions.
    Each LiveKit room gets one AgentSession.
    """

    def __init__(self) -> None:
        self.sessions: dict[str, AgentSession] = {}
        self._running = False

    async def load_agent(self, db: AsyncSession, agent_id: int) -> Optional[AIAgent]:
        result = await db.execute(select(AIAgent).where(AIAgent.id == agent_id, AIAgent.is_active == True))
        return result.scalar_one_or_none()

    async def start_session(
        self,
        room_name: str,
        agent_id: int,
        call_id: int,
        client_id: int,
    ) -> AgentSession:
        async with SessionLocal() as db:
            agent = await self.load_agent(db, agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            session = AgentSession(agent, call_id, client_id, room_name)
            self.sessions[room_name] = session

            result = await db.execute(select(CallLog).where(CallLog.id == call_id))
            call = result.scalar_one_or_none()
            if call:
                call.status = CallStatus.ACTIVE
                await db.commit()

            greeting = await session.get_greeting()
            logger.info("Session started: room=%s agent=%s greeting=%s", room_name, agent.name, greeting[:50])
            return session

    async def handle_audio_transcript(
        self, room_name: str, transcript_text: str
    ) -> Optional[str]:
        session = self.sessions.get(room_name)
        if not session:
            return None

        async with SessionLocal() as db:
            return await session.on_user_speech(transcript_text, db)

    async def end_session(self, room_name: str) -> None:
        session = self.sessions.pop(room_name, None)
        if not session:
            return

        async with SessionLocal() as db:
            result = await db.execute(select(CallLog).where(CallLog.id == session.call_id))
            call = result.scalar_one_or_none()
            if call:
                call.status = CallStatus.COMPLETED
                call.ended_at = datetime.now(timezone.utc)
                if call.started_at:
                    call.duration_seconds = int((call.ended_at - call.started_at).total_seconds())
                await db.commit()

        await socket_manager.emit_call_update(
            session.client_id,
            {"call_id": session.call_id, "status": "completed"},
        )
        logger.info("Session ended: room=%s", room_name)

    async def run(self) -> None:
        """Main worker loop - polls Redis for new call jobs."""
        self._running = True
        logger.info("Agent runtime worker started (concurrency=%d)", settings.WORKER_CONCURRENCY)

        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)

        while self._running:
            try:
                _, job_data = await r.blpop("vbots:call_jobs", timeout=5)
                if job_data:
                    job = json.loads(job_data)
                    await self.start_session(
                        room_name=job["room_name"],
                        agent_id=job["agent_id"],
                        call_id=job["call_id"],
                        client_id=job["client_id"],
                    )
            except Exception as e:
                logger.error("Worker loop error: %s", e)
                await asyncio.sleep(1)


worker = AgentRuntimeWorker()


async def main():
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
