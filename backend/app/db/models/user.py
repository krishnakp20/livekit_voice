import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.client import Client


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    CLIENT_ADMIN = "client_admin"
    MANAGER = "manager"
    AGENT = "agent"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.AGENT)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Optional["Client"]] = relationship(back_populates="users")
