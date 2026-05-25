from typing import Optional

from pydantic import BaseModel


class RecordingResponse(BaseModel):
    call_id: int
    has_recording: bool
    recording_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    size_bytes: Optional[int] = None
    format: str = "ogg"
