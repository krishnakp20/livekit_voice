import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WhatsAppMessageType(str, enum.Enum):
    CALL_SUMMARY = "call_summary"
    MISSED_CALL = "missed_call"
    LEAD_STATUS = "lead_status"
    DAILY_REPORT = "daily_report"


class WhatsAppStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class WhatsAppLog(Base):
    __tablename__ = "whatsapp_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[Optional[int]] = mapped_column(ForeignKey("call_logs.id", ondelete="SET NULL"))
    recipient: Mapped[str] = mapped_column(String(20))
    message_type: Mapped[WhatsAppMessageType] = mapped_column(Enum(WhatsAppMessageType))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[WhatsAppStatus] = mapped_column(Enum(WhatsAppStatus), default=WhatsAppStatus.PENDING)
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
