from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageBilling(Base):
    __tablename__ = "usage_billing"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    billing_period: Mapped[date] = mapped_column(Date, index=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    total_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    ai_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    whatsapp_messages: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    plan: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
