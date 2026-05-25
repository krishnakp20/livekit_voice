import asyncio

from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.whatsapp_tasks.send_daily_reports")
def send_daily_reports():
    asyncio.get_event_loop().run_until_complete(_send_reports())


async def _send_reports():
    from sqlalchemy import func, select

    from app.db.models.call_log import CallLog, CallStatus
    from app.db.models.client import Client
    from app.db.session import AsyncSessionLocal
    from app.services.whatsapp_service import whatsapp_service
    from app.db.models.whatsapp_log import WhatsAppMessageType

    async with AsyncSessionLocal() as db:
        clients = (await db.execute(select(Client).where(Client.is_active == True))).scalars().all()
        for client in clients:
            total = await db.scalar(
                select(func.count(CallLog.id)).where(CallLog.client_id == client.id)
            ) or 0
            completed = await db.scalar(
                select(func.count(CallLog.id)).where(
                    CallLog.client_id == client.id, CallLog.status == CallStatus.COMPLETED
                )
            ) or 0
            if client.phone:
                message = f"📊 Daily Report\nTotal Calls: {total}\nCompleted: {completed}"
                await whatsapp_service.send_message(
                    db, client.id, client.phone, message, WhatsAppMessageType.DAILY_REPORT
                )
        await db.commit()
