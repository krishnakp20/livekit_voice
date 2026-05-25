from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.db.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: DbSession):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login = datetime.now(timezone.utc)
    extra = {"role": user.role.value, "client_id": user.client_id}
    return TokenResponse(
        access_token=create_access_token(user.id, extra),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, db: DbSession, current_user: CurrentUser):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    client_id = data.client_id or current_user.client_id
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        role=data.role,
        client_id=client_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
