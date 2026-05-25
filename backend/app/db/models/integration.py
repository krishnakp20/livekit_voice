import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationType(str, enum.Enum):
    VICIDIAL = "vicidial"
    WHATSAPP = "whatsapp"
    CRM = "crm"
    WEBHOOK = "webhook"


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    integration_type: Mapped[IntegrationType] = mapped_column(Enum(IntegrationType))
    name: Mapped[str] = mapped_column(String(255))
    config_json: Mapped[str] = mapped_column(Text)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
