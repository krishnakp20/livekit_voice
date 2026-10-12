from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, verify_password
from app.db.models.client import Client
from app.db.models.user import User, UserRole
from app.db.session import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # ── Super-admin client context switch ──────────────────────────────────
    # A SUPER_ADMIN can "act as" any client by sending the X-Client-Id header
    # (set by the frontend's client switcher). We override client_id IN MEMORY
    # only — detach from the session first so it is NEVER persisted to the DB.
    if user.role == UserRole.SUPER_ADMIN:
        override = request.headers.get("X-Client-Id")
        if override and override.isdigit():
            db.expunge(user)  # detach: changes below won't be flushed/committed
            user.client_id = int(override)

    return user


async def get_current_active_client_id(
    current_user: Annotated[User, Depends(get_current_user)],
) -> int:
    if current_user.client_id is None and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No client assigned")
    return current_user.client_id


def require_roles(*roles: UserRole):
    async def checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in roles and current_user.role != UserRole.SUPER_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return checker


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.CLIENT_ADMIN, UserRole.SUPER_ADMIN))]
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def verify_client_api_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    client_slug: Annotated[str, Path()],
    x_client_api_key: Annotated[Optional[str], Header()] = None,
) -> Client:
    """Server-to-server auth for lead-ingestion style endpoints (no user login) —
    see POST /leads/ingest/{client_slug}. Scoped to ONE client by slug so this
    only ever checks that client's own key hash, not every client's."""
    if not x_client_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Client-API-Key header")
    result = await db.execute(select(Client).where(Client.slug == client_slug, Client.is_active == True))
    client = result.scalar_one_or_none()
    if not client or not client.api_key_hash or not verify_password(x_client_api_key, client.api_key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client or API key")
    return client


IngestClient = Annotated[Client, Depends(verify_client_api_key)]
