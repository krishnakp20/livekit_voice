from fastapi import APIRouter

from app.api.v1.routes import (
    agents,
    analytics,
    auth,
    calls,
    campaigns,
    clients,
    dispatch,
    integrations,
    leads,
    sip,
    webhooks,
    whatsapp,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(sip.router, prefix="/sip-trunks", tags=["sip"])
api_router.include_router(dispatch.router, prefix="/dispatch", tags=["dispatch"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(whatsapp.router, prefix="/whatsapp", tags=["whatsapp"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
