from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.db.models.ai_agent import AIProvider, Language


class AIAgentCreate(BaseModel):
    # Super admin only: target client for the new agent. Ignored for client admins
    # (their own client_id is always used).
    client_id: Optional[int] = None
    name: str
    language: Language = Language.HINGLISH
    voice: str = "simran"
    gender: str = "female"
    provider: AIProvider = AIProvider.SARVAM
    model: str = "gpt-4o-mini"
    prompt: str = "You are a helpful AI voice agent."
    greeting: str = "Hello! How can I help you today?"
    fallback_message: str = "I'm sorry, I didn't catch that. Could you please repeat?"
    temperature: float = Field(default=0.6, ge=0, le=2)
    max_tokens: int = Field(default=120, ge=50, le=500)
    interruptions_enabled: bool = True
    record_calls: bool = True
    transfer_enabled: bool = False
    transfer_number: Optional[str] = None
    silence_timeout_seconds: int = 30
    business_hours_json: Optional[str] = None
    transfer_rules_json: Optional[str] = None
    data_fields_json: Optional[str] = None
    required_lead_fields: Optional[str] = None
    webhook_json: Optional[str] = None
    # Explicit provider selection. Leave unset (None) to use the server's default
    # priority-chain behaviour. *_api_key here is the PLAINTEXT key — it is
    # encrypted before storage and never echoed back in responses. Blank/omitted
    # key = use the company's global key for that provider.
    stt_provider: Optional[str] = None
    stt_api_key: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    tts_provider: Optional[str] = None
    tts_api_key: Optional[str] = None


class AIAgentUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[Language] = None
    voice: Optional[str] = None
    gender: Optional[str] = None
    provider: Optional[AIProvider] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    greeting: Optional[str] = None
    fallback_message: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    interruptions_enabled: Optional[bool] = None
    record_calls: Optional[bool] = None
    transfer_enabled: Optional[bool] = None
    transfer_number: Optional[str] = None
    silence_timeout_seconds: Optional[int] = None
    business_hours_json: Optional[str] = None
    transfer_rules_json: Optional[str] = None
    data_fields_json: Optional[str] = None
    required_lead_fields: Optional[str] = None
    webhook_json: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_api_key: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    tts_provider: Optional[str] = None
    tts_api_key: Optional[str] = None
    is_active: Optional[bool] = None


class AIAgentResponse(BaseModel):
    id: int
    client_id: int
    name: str
    slug: str
    language: Language
    voice: str
    gender: str
    provider: AIProvider
    model: str
    prompt: str
    greeting: str
    fallback_message: str
    temperature: float
    max_tokens: int
    interruptions_enabled: bool
    record_calls: bool
    transfer_enabled: bool
    transfer_number: Optional[str]
    silence_timeout_seconds: int
    business_hours_json: Optional[str]
    transfer_rules_json: Optional[str]
    data_fields_json: Optional[str]
    required_lead_fields: Optional[str]
    webhook_json: Optional[str]
    stt_provider: Optional[str]
    stt_api_key: Optional[str]   # masked below — never the real (encrypted) value
    llm_provider: Optional[str]
    llm_api_key: Optional[str]   # masked
    tts_provider: Optional[str]
    tts_api_key: Optional[str]   # masked
    livekit_agent_id: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("stt_api_key", "llm_api_key", "tts_api_key", mode="after")
    @classmethod
    def _mask_api_key(cls, v: Optional[str]) -> Optional[str]:
        """Never return the encrypted value — just indicate whether a key is set."""
        return "••••••••" if v else None


class AgentTestRequest(BaseModel):
    message: str


class AgentTestResponse(BaseModel):
    response: str
    latency_ms: int
