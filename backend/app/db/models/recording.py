from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("call_logs.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    format: Mapped[str] = mapped_column(String(20), default="ogg")
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
