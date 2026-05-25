from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.db.models.sip_trunk import TrunkDirection, TrunkStatus


class SIPTrunkCreate(BaseModel):
    name: str
    direction: TrunkDirection
    sip_uri: str
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    did_numbers: Optional[str] = None


class SIPTrunkUpdate(BaseModel):
    name: Optional[str] = None
    sip_uri: Optional[str] = None
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    did_numbers: Optional[str] = None
    is_active: Optional[bool] = None


class SIPTrunkResponse(BaseModel):
    id: int
    client_id: int
    name: str
    direction: TrunkDirection
    status: TrunkStatus
    sip_uri: str
    auth_username: Optional[str]
    did_numbers: Optional[str]
    livekit_trunk_id: Optional[str]
    is_active: bool
    last_tested_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class SIPTrunkTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None
