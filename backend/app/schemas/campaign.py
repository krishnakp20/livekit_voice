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


class LeadIngest(BaseModel):
    """Single-lead push from an external dialer (e.g. VICIdial) — see
    POST /leads/ingest/{client_slug}. Either campaign_id or vicidial_list_id must
    be given; vicidial_list_id is resolved against Campaign.vicidial_list_id so the
    pushing script doesn't need to know VBots' internal campaign id."""
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    campaign_id: Optional[int] = None
    vicidial_list_id: Optional[str] = None
    metadata: Optional[dict] = None


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
