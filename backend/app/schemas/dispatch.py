from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.db.models.dispatch_rule import DispatchType


class DispatchRuleCreate(BaseModel):
    agent_id: int
    rule_type: DispatchType
    match_value: str
    priority: int = 0
    sip_trunk_id: Optional[int] = None


class DispatchRuleUpdate(BaseModel):
    agent_id: Optional[int] = None
    match_value: Optional[str] = None
    priority: Optional[int] = None
    sip_trunk_id: Optional[int] = None
    is_active: Optional[bool] = None


class DispatchRuleResponse(BaseModel):
    id: int
    client_id: int
    agent_id: int
    rule_type: DispatchType
    match_value: str
    priority: int
    sip_trunk_id: Optional[int]
    livekit_rule_id: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
