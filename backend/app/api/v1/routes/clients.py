from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession
from app.db.models.client import Client
from app.db.models.user import User, UserRole
from app.schemas.client import ClientCreate, ClientResponse

router = APIRouter()


@router.get("", response_model=list[ClientResponse])
async def list_clients(db: DbSession, current_user: AdminUser):
    if current_user.role != UserRole.SUPER_ADMIN:
        result = await db.execute(select(Client).where(Client.id == current_user.client_id))
        client = result.scalar_one_or_none()
        return [client] if client else []
    result = await db.execute(select(Client).order_by(Client.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(data: ClientCreate, db: DbSession, current_user: AdminUser):
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super admin only")
    existing = await db.execute(select(Client).where(Client.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")
    client = Client(**data.model_dump())
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return client
