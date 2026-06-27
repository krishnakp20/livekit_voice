import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.client import Client


class AIProvider(str, enum.Enum):
    OPENAI = "openai"
    SARVAM = "sarvam"


class Language(str, enum.Enum):
    ENGLISH = "en-IN"
    HINDI = "hi-IN"
    HINGLISH = "hi-en"


class AIAgent(Base):
    __tablename__ = "ai_agents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), index=True)

    # AI config
    language: Mapped[Language] = mapped_column(Enum(Language), default=Language.HINGLISH)
    voice: Mapped[str] = mapped_column(String(100), default="simran")
    # Persona gender — drives Hindi verb-form grammar ('kar sakti hoon' vs 'kar sakta hoon').
    gender: Mapped[str] = mapped_column(String(10), default="female")
    provider: Mapped[AIProvider] = mapped_column(Enum(AIProvider), default=AIProvider.SARVAM)
    model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    prompt: Mapped[str] = mapped_column(Text, default="You are a helpful AI voice agent.")
    greeting: Mapped[str] = mapped_column(Text, default="Hello! How can I help you today?")
    fallback_message: Mapped[str] = mapped_column(
        Text, default="I'm sorry, I didn't catch that. Could you please repeat?"
    )
    temperature: Mapped[float] = mapped_column(Float, default=0.6)
    max_tokens: Mapped[int] = mapped_column(Integer, default=120)

    # Call behavior
    interruptions_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    record_calls: Mapped[bool] = mapped_column(Boolean, default=True)
    transfer_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_number: Mapped[Optional[str]] = mapped_column(String(20))
    silence_timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)

    # Business hours (JSON string)
    business_hours_json: Mapped[Optional[str]] = mapped_column(Text)
    transfer_rules_json: Mapped[Optional[str]] = mapped_column(Text)
    # Data-collection fields — JSON array of {"key","description"} the bot should
    # capture from the conversation; extracted from the transcript after each call.
    data_fields_json: Mapped[Optional[str]] = mapped_column(Text)
    # Per-lead REQUIRED fields for outbound personalisation. Comma-separated keys
    # (e.g. "customer_name,current_plan_name,whatsapp_link"). A lead missing any of
    # these in its metadata is SKIPPED at dial time (marked FAILED). Optional fields
    # left out here blank out in the prompt and trigger the prompt's own fallback.
    required_lead_fields: Mapped[Optional[str]] = mapped_column(Text)

    # LiveKit
    livekit_agent_id: Mapped[Optional[str]] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="agents")
