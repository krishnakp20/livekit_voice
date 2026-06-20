from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.db.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: UserRole = UserRole.AGENT
    client_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    client_id: Optional[int]
    is_active: bool
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}
