import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.ai_agent import AIAgent
    from app.db.models.user import User


class ClientStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[ClientStatus] = mapped_column(Enum(ClientStatus), default=ClientStatus.TRIAL)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    settings_json: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[List["User"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    agents: Mapped[List["AIAgent"]] = relationship(back_populates="client", cascade="all, delete-orphan")
