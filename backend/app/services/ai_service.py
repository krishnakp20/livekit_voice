"""OpenAI and Sarvam AI provider integration."""

import time
from typing import AsyncGenerator, Optional

import httpx
from openai import AsyncOpenAI

from app.core.config import settings
from app.db.models.ai_agent import AIAgent, AIProvider


class AIService:
    def __init__(self) -> None:
        self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def generate_response(
        self,
        agent: AIAgent,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> tuple[str, int]:
        """Generate LLM response. Returns (text, latency_ms)."""
        start = time.monotonic()
        messages = [{"role": "system", "content": agent.prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        if agent.provider == AIProvider.SARVAM:
            text = await self._sarvam_chat(agent, messages)
        else:
            text = await self._openai_chat(agent, messages)

        latency_ms = int((time.monotonic() - start) * 1000)
        return text, latency_ms

    async def _openai_chat(self, agent: AIAgent, messages: list[dict]) -> str:
        if not self._openai:
            return agent.fallback_message
        response = await self._openai.chat.completions.create(
            model=agent.model,
            messages=messages,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )
        return response.choices[0].message.content or agent.fallback_message

    async def _sarvam_chat(self, agent: AIAgent, messages: list[dict]) -> str:
        """Sarvam AI chat completion."""
        if not settings.SARVAM_API_KEY:
            return await self._openai_chat(agent, messages)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers={"api-subscription-key": settings.SARVAM_API_KEY},
                json={
                    "model": agent.model,
                    "messages": messages,
                    "temperature": agent.temperature,
                    "max_tokens": agent.max_tokens,
                },
                timeout=30.0,
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
        return agent.fallback_message

    async def stream_response(
        self,
        agent: AIAgent,
        user_message: str,
    ) -> AsyncGenerator[str, None]:
        if not self._openai:
            yield agent.fallback_message
            return
        stream = await self._openai.chat.completions.create(
            model=agent.model,
            messages=[
                {"role": "system", "content": agent.prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    _SENTIMENT_SYSTEM = (
        "You score caller sentiment on a customer-service phone call. "
        "Text may be Hindi, English, or Hinglish. "
        "Score from -1 (angry, hostile, very frustrated) to 1 (happy, thankful, very satisfied). "
        "Use 0 for neutral: information requests, bookings, clarifications, normal back-and-forth. "
        "Words like Hindi 'nahi' or English 'no' that correct the agent (e.g. 'no, I meant flights not hotel') "
        "are NOT negative unless the caller sounds upset. "
        "Reply with only one number between -1 and 1 (e.g. 0.2 or -0.5)."
    )

    async def analyze_sentiment(self, text: str) -> float:
        """Return sentiment score -1 to 1 for a single utterance or combined caller text."""
        return await self.analyze_call_sentiment(text)

    async def analyze_call_sentiment(self, caller_text: str) -> float:
        """Score overall caller tone; neutral inquiries should be near 0."""
        if not self._openai or not (caller_text or "").strip():
            return 0.0
        response = await self._openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": self._SENTIMENT_SYSTEM},
                {"role": "user", "content": caller_text.strip()},
            ],
            max_tokens=10,
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip()
        try:
            score = float(raw.split()[0].rstrip(".,;"))
            return max(-1.0, min(1.0, score))
        except (ValueError, AttributeError, IndexError):
            return 0.0


ai_service = AIService()
