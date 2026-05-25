from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.services.analytics_service import analytics_service

router = APIRouter()


@router.get("/dashboard")
async def dashboard(db: DbSession, current_user: CurrentUser, days: int = 30):
    return await analytics_service.get_dashboard_stats(db, current_user.client_id, days)


@router.get("/agents")
async def agent_performance(db: DbSession, current_user: CurrentUser, days: int = 30):
    return await analytics_service.get_agent_performance(db, current_user.client_id, days)
