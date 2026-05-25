import asyncio

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.campaign_tasks.process_scheduled_campaigns")
def process_scheduled_campaigns():
    """Dial leads for RUNNING campaigns (every 5 min via Celery Beat)."""
    asyncio.run(_process())


async def _process():
    from sqlalchemy import select

    from app.db.models.campaign import Campaign, CampaignStatus
    from app.db.session import AsyncSessionLocal
    from app.services.campaign_dial_service import dial_campaign_leads

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.RUNNING)
        )
        for campaign in result.scalars().all():
            try:
                await dial_campaign_leads(db, campaign.id)
            except Exception:
                import logging

                logging.getLogger("vbots.campaign_dial").exception(
                    "Scheduled dial failed campaign_id=%s", campaign.id
                )
