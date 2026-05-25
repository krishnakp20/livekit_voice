import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DispatchType(str, enum.Enum):
    DID = "did"
    TRUNK = "trunk"
    CAMPAIGN = "campaign"
    INGROUP = "ingroup"


class DispatchRule(Base):
    __tablename__ = "dispatch_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("ai_agents.id", ondelete="CASCADE"), index=True)
    rule_type: Mapped[DispatchType] = mapped_column(Enum(DispatchType))
    match_value: Mapped[str] = mapped_column(String(255), index=True)  # DID, trunk ID, campaign, ingroup
    priority: Mapped[int] = mapped_column(Integer, default=0)
    sip_trunk_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sip_trunks.id", ondelete="SET NULL"))
    livekit_rule_id: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
