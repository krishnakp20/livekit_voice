import asyncio

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.campaign_tasks.process_scheduled_campaigns")
def process_scheduled_campaigns():
    """Dial leads for RUNNING campaigns (every 20s via Celery Beat)."""
    asyncio.run(_process())


async def _process():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.db.models.campaign import Campaign, CampaignStatus
    from app.services.campaign_dial_service import dial_campaign_leads

    # Celery runs asyncio.run() per task → a NEW event loop each time. The shared
    # app engine's connection pool is bound to a different loop, which raises
    # "Future attached to a different loop". So build a throwaway engine with
    # NullPool (no cross-loop connection reuse) and dispose it when done.
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            result = await db.execute(
                select(Campaign).where(Campaign.status == CampaignStatus.RUNNING)
            )
            campaigns = result.scalars().all()
            for campaign in campaigns:
                try:
                    await dial_campaign_leads(db, campaign.id)
                except Exception:
                    import logging

                    logging.getLogger("vbots.campaign_dial").exception(
                        "Scheduled dial failed campaign_id=%s", campaign.id
                    )
    finally:
        await engine.dispose()
