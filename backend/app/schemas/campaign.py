from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.db.models.campaign import CampaignStatus, LeadStatus


class CampaignCreate(BaseModel):
    name: str
    agent_id: int
    scheduled_at: Optional[datetime] = None
    max_retries: int = 3
    retry_interval_minutes: int = 60
    dial_rate: int = 1


class CampaignResponse(BaseModel):
    id: int
    client_id: int
    agent_id: int
    name: str
    status: CampaignStatus
    scheduled_at: Optional[datetime]
    max_retries: int
    retry_interval_minutes: int
    dial_rate: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadCreate(BaseModel):
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    campaign_id: Optional[int] = None
    metadata_json: Optional[str] = None


class LeadResponse(BaseModel):
    id: int
    client_id: int
    campaign_id: Optional[int]
    phone: str
    name: Optional[str]
    email: Optional[str]
    status: LeadStatus
    retry_count: int
    last_called_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
