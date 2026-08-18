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
        # Groq as fallback for sentiment when OpenAI quota is exhausted
        self._groq: AsyncOpenAI | None = None
        _groq_key = settings.GROQ_API_KEY if hasattr(settings, "GROQ_API_KEY") else __import__("os").getenv("GROQ_API_KEY", "")
        if _groq_key:
            self._groq = AsyncOpenAI(
                api_key=_groq_key,
                base_url="https://api.groq.com/openai/v1",
            )

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
        """Score overall caller tone; neutral inquiries should be near 0.
        Uses Groq (llama-3.3-70b) preferentially; falls back to OpenAI gpt-4o-mini."""
        if not (caller_text or "").strip():
            return 0.0

        messages = [
            {"role": "system", "content": self._SENTIMENT_SYSTEM},
            {"role": "user", "content": caller_text.strip()},
        ]

        # Try Groq first (fast + free tier available)
        client = self._groq or self._openai
        model = "llama-3.3-70b-versatile" if self._groq else "gpt-4o-mini"
        if not client:
            return 0.0

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=10,
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip()
        try:
            score = float(raw.split()[0].rstrip(".,;"))
            return max(-1.0, min(1.0, score))
        except (ValueError, AttributeError, IndexError):
            return 0.0


    async def extract_call_data(self, transcript: str, fields: list[dict]) -> dict:
        """Extract structured fields from a call transcript.

        `fields` is a list like [{"key": "name", "description": "customer name"}, ...].
        Returns a dict {key: value | null}. Uses Groq (fast) then OpenAI fallback.
        """
        import json

        if not (transcript or "").strip() or not fields:
            return {}

        field_lines = "\n".join(
            f"- {f.get('key')}: {f.get('description', f.get('key'))}" for f in fields if f.get("key")
        )
        keys = [f["key"] for f in fields if f.get("key")]
        system = (
            "You extract structured information from a customer-service phone call "
            "transcript (Hindi, English, or Hinglish). Extract ONLY these fields:\n"
            f"{field_lines}\n\n"
            "Rules:\n"
            "- Return a single JSON object with exactly these keys: "
            f"{', '.join(keys)}.\n"
            "- If a field was not mentioned or is unclear, set it to null.\n"
            "- ALWAYS write values in ENGLISH. Translate or transliterate Hindi and "
            "Devanagari into English (कृष्णा → Krishna, दिल्ली → Delhi, "
            "सोलर पैनल → Solar Panel). NEVER return Devanagari script.\n"
            "- Convert spoken numbers into digits: 'six forty three' → 643, "
            "'double nine' → 99, 'ninety two' → 92, 'दस' → 10.\n"
            "- Phone numbers: digits only, exactly 10 digits for an Indian mobile. "
            "Rebuild carefully from spoken digits ('double nine' = 99). If the result "
            "is not 10 digits, return null rather than a wrong number.\n"
            "- If a field's description says not to capture/use the 'incoming' or "
            "'calling' number, that refers only to the caller-ID metadata of this "
            "call — a value that is NOT present anywhere in this transcript. It does "
            "NOT mean you should skip a phone number the customer states out loud "
            "during the conversation. Always extract a number the customer actually "
            "speaks and confirms in the transcript.\n"
            "- Include the unit when the customer implies one: capacity → '4 kW', "
            "pump → '5 HP'.\n"
            "- Format an address as one clean postal line, e.g. "
            "'643, Ground Floor, Sabkapur, Delhi - 110092'.\n"
            "- Use Title Case for names, cities and states.\n"
            "- For any description or summary field, write ONE concise English "
            "sentence describing what the customer wants.\n"
            "- Do not invent values. Return ONLY the JSON, no extra text."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript.strip()[:6000]},
        ]

        # Prefer OpenAI: extraction runs once per call and feeds the CRM push, so a
        # Groq free-tier 429 here would silently drop the whole payload.
        client = self._openai or self._groq
        model = "gpt-4o-mini" if self._openai else "llama-3.3-70b-versatile"
        if not client:
            return {}

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=400,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "").strip()
            data = json.loads(raw)
            # Keep only the declared keys
            return {k: data.get(k) for k in keys}
        except Exception:
            return {}


ai_service = AIService()
