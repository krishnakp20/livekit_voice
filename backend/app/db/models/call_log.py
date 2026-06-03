import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CallDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(str, enum.Enum):
    RINGING = "ringing"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    TRANSFERRED = "transferred"
    MISSED = "missed"


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_agents.id", ondelete="SET NULL"))
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    lead_id: Mapped[Optional[int]] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))

    room_name: Mapped[str] = mapped_column(String(255), index=True)
    call_sid: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    direction: Mapped[CallDirection] = mapped_column(Enum(CallDirection))
    status: Mapped[CallStatus] = mapped_column(Enum(CallStatus), default=CallStatus.RINGING)
    caller_number: Mapped[Optional[str]] = mapped_column(String(20))
    callee_number: Mapped[Optional[str]] = mapped_column(String(20))
    did_number: Mapped[Optional[str]] = mapped_column(String(20))

    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)

    # ── Usage + cost tracking (populated by worker at call end) ──────────────
    stt_audio_seconds: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    llm_prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    llm_completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    tts_characters: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    stt_cost: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    llm_cost: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    tts_cost: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    total_cost: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    disposition: Mapped[Optional[str]] = mapped_column(String(100))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)

    vicidial_lead_id: Mapped[Optional[str]] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
