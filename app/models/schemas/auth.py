"""Authentication Pydantic schemas."""
import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from app.models.database.user import UserRole


def _validate_password_strength(v: str) -> str:
    """SEC-013: Enforce minimum password complexity requirements."""
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit")
    if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in v):
        raise ValueError("Password must contain at least one special character")
    return v


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    role: UserRole = UserRole.FACULTY
    institution_id: Optional[str] = None
    department: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("Username may only contain letters, digits, underscores, dots, and hyphens")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    role: UserRole
    institution_id: Optional[str]
    department: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)