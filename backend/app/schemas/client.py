from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.db.models.client import ClientStatus


class ClientCreate(BaseModel):
    name: str
    slug: str
    email: EmailStr
    phone: Optional[str] = None
    timezone: str = "Asia/Kolkata"


class ClientResponse(BaseModel):
    id: int
    name: str
    slug: str
    email: str
    phone: Optional[str]
    status: ClientStatus
    timezone: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
