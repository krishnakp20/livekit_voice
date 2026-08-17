import os
import socket

from fastapi import APIRouter

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.services.analytics_service import analytics_service

router = APIRouter()


@router.get("/dashboard_old")
async def dashboard_old(db: DbSession, current_user: CurrentUser, days: int = 30):
    return await analytics_service.get_dashboard_stats_old(db, current_user.client_id, days)

@router.get("/dashboard")
async def dashboard(db: DbSession, current_user: CurrentUser, days: int = 30):
    return await analytics_service.get_dashboard_stats(db, current_user.client_id, days)

@router.get("/call-volume")
async def call_volume(db: DbSession, current_user: CurrentUser, days: int = 14):
    return await analytics_service.get_call_volume_trend(db, current_user.client_id, days)

@router.get("/call-outcome")
async def call_outcome(db: DbSession, current_user: CurrentUser):
    return await analytics_service.get_call_outcome_distribution(db, current_user.client_id)

@router.get("/agent-performance")
async def agent_performance(db: DbSession, current_user: CurrentUser):
    return await analytics_service.get_agent_performance_ranking(db, current_user.client_id)

@router.get("/call-duration")
async def call_duration(db: DbSession, current_user: CurrentUser):
    return await analytics_service.get_call_duration_analysis(db, current_user.client_id)

@router.get("/business-performance")
async def business_performance(db: DbSession, current_user: CurrentUser):
    return await analytics_service.get_business_performance(db, current_user.client_id)

@router.get("/agent-postive-rate")
async def agent_postive_rate(db: DbSession, current_user: CurrentUser, days: int = 7):
    return await analytics_service.get_agent_positive_rate(db, current_user.client_id, days)

@router.get("/technical-metrics")
async def technical_metrics(db: DbSession, current_user: CurrentUser):
    return await analytics_service.get_technical_metrics(db, current_user.client_id)


@router.get("/agents")
async def agent_performance(db: DbSession, current_user: CurrentUser, days: int = 30):
    return await analytics_service.get_agent_performance(db, current_user.client_id, days)


@router.get("/campaigns")
async def campaign_performance(db: DbSession, current_user: CurrentUser):
    return await analytics_service.get_campaign_performance(db, current_user.client_id)


def _tcp_ok(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@router.get("/health")
async def system_health(db: DbSession, current_user: CurrentUser):
    """Live status of the platform's core services for the dashboard health row."""
    # LiveKit (parse host:port from ws(s):// URL)
    lk_host, lk_port = "localhost", 7880
    try:
        netloc = settings.LIVEKIT_URL.split("://", 1)[-1].split("/", 1)[0]
        if ":" in netloc:
            lk_host, p = netloc.rsplit(":", 1)
            lk_port = int(p)
        else:
            lk_host = netloc
    except Exception:
        pass

    livekit_ok = _tcp_ok(lk_host, lk_port)

    # DB
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # Asterisk / SIP trunk host — best-effort TCP check on the trunk's SIP host:5060
    sip_host = (getattr(settings, "SIP_TRANSFER_HOST", "") or "").strip()
    sip_ok = _tcp_ok(sip_host, 5060) if sip_host else None

    def status(ok):
        return "operational" if ok else ("down" if ok is False else "unknown")

    # AI providers — "configured" = API key present (we don't ping them every poll)
    deepgram = bool(os.getenv("DEEPGRAM_API_KEY"))
    cartesia = bool(os.getenv("CARTESIA_API_KEY"))
    sarvam = bool(settings.SARVAM_API_KEY)
    openai_k = bool(os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY)
    groq_k = bool(os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", ""))

    return {
        "livekit": status(livekit_ok),
        "asterisk": status(sip_ok),         # SIP trunk host reachability
        "sip_trunk": status(sip_ok),
        "database": status(db_ok),
        "stt": "configured" if deepgram or sarvam else "not configured",
        "tts": "configured" if cartesia or sarvam else "not configured",
        "llm": "configured" if openai_k or groq_k else "not configured",
    }
