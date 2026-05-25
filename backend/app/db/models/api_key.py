from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(10))
    scopes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
