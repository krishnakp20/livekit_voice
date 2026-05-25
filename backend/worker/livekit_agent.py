"""
LiveKit Agents SDK integration example.

Connects to LiveKit rooms and pipes audio through STT → LLM → TTS pipeline.
Uses dynamic agent config from database.
"""

import asyncio
import json
import logging

from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice import Agent as VoiceAgent
from livekit.agents.voice import AgentSession

from app.core.config import settings

logger = logging.getLogger("vbots.livekit_agent")


async def entrypoint(ctx: JobContext):
    """LiveKit agent entrypoint - called when a SIP call creates a room."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    metadata = json.loads(ctx.room.metadata or "{}")
    agent_id = metadata.get("agent_id")
    client_id = metadata.get("client_id")

    logger.info("Joining room %s for agent_id=%s", ctx.room.name, agent_id)

    from worker.agent_runtime import AgentRuntimeWorker, SessionLocal
    from app.db.models.ai_agent import AIAgent
    from sqlalchemy import select

    runtime = AgentRuntimeWorker()

    async with SessionLocal() as db:
        result = await db.execute(select(AIAgent).where(AIAgent.id == agent_id))
        agent_config = result.scalar_one_or_none()

    if not agent_config:
        logger.error("Agent %s not found", agent_id)
        return

    voice_agent = VoiceAgent(
        instructions=agent_config.prompt,
        llm=llm.LLM(model=agent_config.model),
    )

    session = AgentSession(agent=voice_agent)
    await session.start(ctx.room)

    greeting = agent_config.greeting
    await session.say(greeting)

    @ctx.room.on("track_subscribed")
    def on_track(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info("Audio track from %s", participant.identity)


def run_worker():
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )
    )


if __name__ == "__main__":
    run_worker()
