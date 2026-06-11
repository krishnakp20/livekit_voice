from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.db.models.call_log import CallDirection, CallStatus
from app.db.models.transcript import SpeakerRole


class TranscriptEntry(BaseModel):
    id: int
    speaker: SpeakerRole
    content: str
    llm_response: Optional[str]
    latency_ms: Optional[int]
    sentiment: Optional[float]
    sequence: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CallLogResponse(BaseModel):
    id: int
    client_id: int
    agent_id: Optional[int]
    room_name: str
    direction: CallDirection
    status: CallStatus
    caller_number: Optional[str]
    callee_number: Optional[str]
    did_number: Optional[str]
    duration_seconds: Optional[int]
    sentiment_score: Optional[float]
    disposition: Optional[str]
    summary: Optional[str]
    collected_data: Optional[str] = None
    total_cost: Optional[float] = None
    started_at: datetime
    ended_at: Optional[datetime]
    transcripts: List[TranscriptEntry] = []
    has_recording: bool = False
    recording_url: Optional[str] = None

    model_config = {"from_attributes": True}


class LiveCallResponse(BaseModel):
    call_id: int
    room_name: str
    agent_name: str
    caller_number: Optional[str]
    duration_seconds: int
    status: CallStatus
    agent_speaking: bool
    user_speaking: bool
    latest_transcript: Optional[str]
    sentiment_score: Optional[float]
