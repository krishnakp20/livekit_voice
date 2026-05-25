import json

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.integration import Integration, IntegrationType

router = APIRouter()


class IntegrationCreate(BaseModel):
    integration_type: IntegrationType
    name: str
    config_json: dict
    webhook_url: str | None = None


@router.get("")
async def list_integrations(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(Integration).where(Integration.client_id == current_user.client_id)
    )
    return [
        {
            "id": i.id,
            "name": i.name,
            "integration_type": i.integration_type.value,
            "is_active": i.is_active,
            "created_at": i.created_at.isoformat(),
        }
        for i in result.scalars().all()
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_integration(data: IntegrationCreate, db: DbSession, current_user: AdminUser):
    integration = Integration(
        client_id=current_user.client_id,
        integration_type=data.integration_type,
        name=data.name,
        config_json=json.dumps(data.config_json),
        webhook_url=data.webhook_url,
    )
    db.add(integration)
    await db.flush()
    return {"id": integration.id, "name": integration.name}
