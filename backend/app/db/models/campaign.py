import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    DIALING = "dialing"
    CONNECTED = "connected"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    CONVERTED = "converted"
    DNC = "dnc"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("ai_agents.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(Enum(CampaignStatus), default=CampaignStatus.DRAFT)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Attempts-per-day cap (e.g. 3). Combined with max_days below, a lead gets at
    # most max_retries x max_days total attempts before it exits the calling list.
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    # Gap between attempts, in minutes (e.g. 120 for Saatvik's 2-hour cadence).
    # Previously stored but never read anywhere — now wired into the retry
    # state machine in worker/agent.py's call-end handler.
    retry_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    dial_rate: Mapped[int] = mapped_column(Integer, default=1)
    # Calling window (local server time, 24h clock) — leads are never dialed
    # outside [calling_window_start_hour, calling_window_end_hour). A retry that
    # would land outside this window is pushed to the next day's start instead.
    # NULL on either = no window restriction (today's always-on behaviour).
    calling_window_start_hour: Mapped[Optional[int]] = mapped_column(Integer)
    calling_window_end_hour: Mapped[Optional[int]] = mapped_column(Integer)
    # How many calendar days the cadence runs before a lead exits for good
    # (e.g. 3, for Saatvik's "3 attempts/day x 3 days" = 9 total attempts).
    max_days: Mapped[int] = mapped_column(Integer, default=1)
    vicidial_list_id: Mapped[Optional[str]] = mapped_column(String(100))
    settings_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    # Cadence state (see campaign_dial_service.compute_lead_retry_update). Unused
    # (stay at their defaults) for campaigns that haven't set Campaign.max_days > 1
    # or a calling_window — those keep the original immediate-retry behaviour.
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    day_count: Mapped[int] = mapped_column(Integer, default=1)
    attempts_today: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    last_called_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
