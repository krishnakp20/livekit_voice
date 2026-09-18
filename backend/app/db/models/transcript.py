import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SpeakerRole(str, enum.Enum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("call_logs.id", ondelete="CASCADE"), index=True)
    speaker: Mapped[SpeakerRole] = mapped_column(Enum(SpeakerRole))
    content: Mapped[str] = mapped_column(Text)
    llm_response: Mapped[Optional[str]] = mapped_column(Text)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    # Per-stage timing for the dashboard's transcript view (ASR badge on user turns;
    # LLM/TTS badges on agent turns). Populated from the same _TurnBucket metrics
    # already used for the worker's LATENCY BREAKDOWN log lines.
    stt_ms: Mapped[Optional[int]] = mapped_column(Integer)
    llm_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tts_ms: Mapped[Optional[int]] = mapped_column(Integer)
    sentiment: Mapped[Optional[float]] = mapped_column(Float)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
