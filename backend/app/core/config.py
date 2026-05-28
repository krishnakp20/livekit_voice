import json
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of process cwd (worker dev watcher, etc.)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


def _split_cors_origins(value: str) -> List[str]:
    default = ["http://localhost:5173", "http://localhost:3000"]
    if not value or not value.strip():
        return default
    s = value.strip()
    if s.startswith("["):
        return json.loads(s)
    return [origin.strip() for origin in s.split(",") if origin.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "VBots AI Calling Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database (MySQL)
    DATABASE_URL: str = "mysql+aiomysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4"
    DATABASE_URL_SYNC: str = "mysql+pymysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # CORS — store as string in .env (comma-separated); use cors_origins_list in app code
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> List[str]:
        return _split_cors_origins(self.CORS_ORIGINS)

    # LiveKit
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_SIP_URI: str = "sip:localhost"
    # Match LiveKit Agent Dispatch name; leave empty if your SIP dispatch accepts any worker
    LIVEKIT_AGENT_NAME: str = ""
    # Outbound SIP trunk LiveKit ID (ST_xxx) — set this so campaign/outbound dials skip DB lookup.
    # Get it from SIP Trunks page → Sync from LiveKit, then copy the livekit_trunk_id value.
    LIVEKIT_OUTBOUND_TRUNK_ID: str = ""

    # AI Providers
    OPENAI_API_KEY: str = ""
    SARVAM_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"

    # Storage
    RECORDINGS_PATH: str = "/data/recordings"
    # Optional fallback only — normal recordings use AgentSession.start(record=...)
    LIVEKIT_EGRESS_RECORDING: bool = False
    LIVEKIT_EGRESS_OUTPUT_DIR: str = ""
    UPLOADS_PATH: str = "/data/uploads"

    # WhatsApp (Meta Cloud API)
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v18.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""

    # VICIdial
    VICIDIAL_WEBHOOK_SECRET: str = ""

    # Worker / voice agent tuning
    WORKER_CONCURRENCY: int = 10
    SILENCE_TIMEOUT_SECONDS: int = 30
    # Sarvam — saaras:v3 + bulbul:v3 match the working vbot agent (clearer STT/TTS on SIP)
    AGENT_STT_MODEL: str = "saaras:v3"
    AGENT_TTS_MODEL: str = "bulbul:v3"
    AGENT_STT_PROMPT: str = (
        "Indian phone call in Hindi or Hinglish. "
        "Topics: flights, tickets, hotels, travel dates, cities like Delhi Mumbai. "
        "Transcribe what the caller actually said; do not guess unrelated words."
    )
    AGENT_PREEMPTIVE_GENERATION: bool = False
    # Turn detection mode for AgentSession (livekit-agents v1.5+):
    #   "stt"  — STT final transcript drives EOU (Deepgram endpointing_ms=100). NOT affected by
    #            SIP background noise. Fastest + most reliable on noisy phone lines. (recommended)
    #   "vad"  — Silero VAD silence threshold. Fast but confused by continuous background hiss.
    #   "realtime_llm" — OpenAI Realtime API only; not used here.
    AGENT_TURN_DETECTION: str = "stt"
    AGENT_MIN_ENDPOINTING_DELAY: float = 0.20   # was 0.30 — saves 100ms per turn
    # semantic mode decides EOU quickly from content; 1.5 s safety net is enough (was 2.5 s)
    AGENT_MAX_ENDPOINTING_DELAY: float = 1.5
    AGENT_REPLY_MAX_TOKENS: int = 80
    # STT / RoomIO sample rate — must match SIP trunk (8 kHz narrowband PSTN)
    AGENT_AUDIO_SAMPLE_RATE: int = 8000
    # TTS generates at this rate; LiveKit resamples DOWN to AGENT_AUDIO_SAMPLE_RATE for SIP.
    # Use the TTS model's native rate (22050 Hz) so the neural model produces full-quality audio
    # before the codec step — better than asking the model to output 8 kHz directly.
    AGENT_TTS_SAMPLE_RATE: int = 22050

    # Auto-close DB rows stuck in ringing/active (Live Calls / dashboard)
    LIVE_CALL_RINGING_MAX_SECONDS: int = 300  # 5 min still ringing → missed
    LIVE_CALL_ACTIVE_MAX_SECONDS: int = 600  # 10 min still active → completed
    # Failed OB / worker timeout: close + delete LiveKit room if older than this
    LIVE_CALL_ORPHAN_SECONDS: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
