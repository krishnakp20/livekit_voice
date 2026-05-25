import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrunkDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class TrunkStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TESTING = "testing"


class SIPTrunk(Base):
    __tablename__ = "sip_trunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[TrunkDirection] = mapped_column(Enum(TrunkDirection))
    status: Mapped[TrunkStatus] = mapped_column(Enum(TrunkStatus), default=TrunkStatus.INACTIVE)

    # SIP credentials
    sip_uri: Mapped[str] = mapped_column(String(500))
    auth_username: Mapped[Optional[str]] = mapped_column(String(255))
    auth_password: Mapped[Optional[str]] = mapped_column(String(255))
    did_numbers: Mapped[Optional[str]] = mapped_column(Text)  # comma-separated

    # LiveKit mapping
    livekit_trunk_id: Mapped[Optional[str]] = mapped_column(String(255))
    livekit_dispatch_rule_id: Mapped[Optional[str]] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
