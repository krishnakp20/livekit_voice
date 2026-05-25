from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.campaign import Campaign, CampaignStatus, Lead, LeadStatus
from app.schemas.campaign import CampaignCreate, CampaignResponse
from app.services.campaign_dial_service import dial_campaign_leads

router = APIRouter()


class CampaignStatusUpdate(BaseModel):
    status: CampaignStatus


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Campaign)
        .where(Campaign.client_id == current_user.client_id)
        .order_by(Campaign.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(data: CampaignCreate, db: DbSession, current_user: AdminUser):
    campaign = Campaign(client_id=current_user.client_id, **data.model_dump())
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: int, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.client_id == current_user.client_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/{campaign_id}/stats")
async def campaign_stats(campaign_id: int, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.client_id == current_user.client_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    counts = await db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.campaign_id == campaign_id)
        .group_by(Lead.status)
    )
    by_status = {row[0].value: row[1] for row in counts.all()}
    return {
        "campaign_id": campaign_id,
        "leads": by_status,
        "total": sum(by_status.values()),
    }


@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
async def update_campaign_status(
    campaign_id: int,
    body: CampaignStatusUpdate,
    db: DbSession,
    current_user: AdminUser,
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.client_id == current_user.client_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = body.status
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/dial")
async def dial_campaign_now(
    campaign_id: int,
    db: DbSession,
    current_user: AdminUser,
    limit: int | None = None,
):
    """Dial next batch of NEW leads immediately (no Celery required)."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.client_id == current_user.client_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        outcome = await dial_campaign_leads(db, campaign_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return outcome
