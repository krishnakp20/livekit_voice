from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.db.models.whatsapp_log import WhatsAppLog

router = APIRouter()


@router.get("/logs")
async def list_whatsapp_logs(db: DbSession, current_user: CurrentUser, skip: int = 0, limit: int = 50):
    result = await db.execute(
        select(WhatsAppLog)
        .where(WhatsAppLog.client_id == current_user.client_id)
        .order_by(WhatsAppLog.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "recipient": l.recipient,
            "message_type": l.message_type.value,
            "status": l.status.value,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]
