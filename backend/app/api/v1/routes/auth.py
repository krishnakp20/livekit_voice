from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_reset_token,
    get_password_hash,
    verify_password,
    verify_reset_token,
)
from app.db.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)

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


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: DbSession):
    """Email a password-reset link. Always returns success (never reveals whether
    the email exists) to avoid account enumeration."""
    from app.services.email_service import send_password_reset_email

    result = await db.execute(select(User).where(User.email == data.email, User.is_active == True))
    user = result.scalar_one_or_none()
    if user:
        token = create_reset_token(user.id)
        reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        send_password_reset_email(user.email, reset_link)

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: DbSession):
    """Validate the reset token and set a new password."""
    user_id = verify_reset_token(data.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = get_password_hash(data.new_password)
    await db.commit()
    return {"message": "Password updated. You can now log in with your new password."}


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
