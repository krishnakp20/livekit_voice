"""WhatsApp Cloud API integration."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.whatsapp_log import WhatsAppLog, WhatsAppMessageType, WhatsAppStatus


class WhatsAppService:
    async def send_message(
        self,
        db: AsyncSession,
        client_id: int,
        recipient: str,
        message: str,
        message_type: WhatsAppMessageType,
        call_id: int | None = None,
    ) -> WhatsAppLog:
        log = WhatsAppLog(
            client_id=client_id,
            call_id=call_id,
            recipient=recipient,
            message_type=message_type,
            content=message,
            status=WhatsAppStatus.PENDING,
        )
        db.add(log)
        await db.flush()

        if settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                        headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                        json={
                            "messaging_product": "whatsapp",
                            "to": recipient.replace("+", ""),
                            "type": "text",
                            "text": {"body": message},
                        },
                        timeout=30.0,
                    )
                    if response.status_code == 200:
                        log.status = WhatsAppStatus.SENT
                        log.external_id = response.json().get("messages", [{}])[0].get("id")
                    else:
                        log.status = WhatsAppStatus.FAILED
                        log.error_message = response.text
            except Exception as e:
                log.status = WhatsAppStatus.FAILED
                log.error_message = str(e)
        else:
            log.status = WhatsAppStatus.SENT  # dev mode

        return log

    async def send_call_summary(
        self, db: AsyncSession, client_id: int, recipient: str, summary: str, call_id: int
    ) -> WhatsAppLog:
        message = f"📞 Call Summary\n\n{summary}"
        return await self.send_message(
            db, client_id, recipient, message, WhatsAppMessageType.CALL_SUMMARY, call_id
        )

    async def send_missed_call_alert(
        self, db: AsyncSession, client_id: int, recipient: str, caller: str, call_id: int
    ) -> WhatsAppLog:
        message = f"⚠️ Missed Call from {caller}"
        return await self.send_message(
            db, client_id, recipient, message, WhatsAppMessageType.MISSED_CALL, call_id
        )


whatsapp_service = WhatsAppService()
