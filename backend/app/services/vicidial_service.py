"""VICIdial integration: lead sync, disposition, webhooks."""

import hashlib
import hmac
import json
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.call_log import CallLog
from app.db.models.integration import Integration, IntegrationType


class VICIdialService:
    async def get_integration(self, db: AsyncSession, client_id: int) -> Optional[Integration]:
        result = await db.execute(
            select(Integration).where(
                Integration.client_id == client_id,
                Integration.integration_type == IntegrationType.VICIDIAL,
                Integration.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def sync_lead(
        self,
        db: AsyncSession,
        client_id: int,
        lead_data: dict[str, Any],
    ) -> dict[str, Any]:
        integration = await self.get_integration(db, client_id)
        if not integration:
            return {"success": False, "error": "VICIdial not configured"}

        config = json.loads(integration.config_json)
        base_url = config.get("api_url", "").rstrip("/")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/vicidial/non_agent_api.php",
                data={
                    "function": "add_lead",
                    "user": config.get("api_user"),
                    "pass": config.get("api_pass"),
                    "source": "vbots",
                    "phone_number": lead_data.get("phone"),
                    "first_name": lead_data.get("name", ""),
                    "list_id": lead_data.get("list_id", config.get("default_list_id")),
                },
                timeout=30.0,
            )
            return {"success": response.status_code == 200, "data": response.text}

    async def update_disposition(
        self,
        db: AsyncSession,
        call: CallLog,
        disposition: str,
    ) -> dict[str, Any]:
        integration = await self.get_integration(db, call.client_id)
        if not integration or not call.vicidial_lead_id:
            return {"success": False}

        config = json.loads(integration.config_json)
        base_url = config.get("api_url", "").rstrip("/")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/vicidial/non_agent_api.php",
                data={
                    "function": "update_lead",
                    "user": config.get("api_user"),
                    "pass": config.get("api_pass"),
                    "lead_id": call.vicidial_lead_id,
                    "status": disposition,
                },
                timeout=30.0,
            )
            return {"success": response.status_code == 200}

    async def handle_webhook(
        self,
        db: AsyncSession,
        client_id: int,
        event: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle inbound VICIdial webhooks (call events, lead updates)."""
        handlers = {
            "call_started": self._on_call_started,
            "call_ended": self._on_call_ended,
            "lead_updated": self._on_lead_updated,
        }
        handler = handlers.get(event)
        if handler:
            return await handler(db, client_id, data)
        return {"success": False, "error": f"Unknown event: {event}"}

    async def _on_call_started(self, db: AsyncSession, client_id: int, data: dict) -> dict:
        return {"success": True, "action": "call_started_ack"}

    async def _on_call_ended(self, db: AsyncSession, client_id: int, data: dict) -> dict:
        return {"success": True, "action": "call_ended_ack"}

    async def _on_lead_updated(self, db: AsyncSession, client_id: int, data: dict) -> dict:
        return {"success": True, "action": "lead_updated_ack"}


vicidial_service = VICIdialService()
