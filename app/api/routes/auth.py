"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import logging

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.schemas.auth import UserCreate, UserLogin, UserResponse, TokenResponse, RefreshTokenRequest, PasswordChangeRequest
from app.services.auth.auth_service import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.api.dependencies.auth_deps import get_current_active_user
from app.utils.helpers import generate_uuid
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail={"message": "Email already registered", "code": "EMAIL_EXISTS"})

    # Check username
    result = await db.execute(select(User).where(User.username == user_in.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail={"message": "Username already taken", "code": "USERNAME_EXISTS"})

    user = User(
        id=generate_uuid(),
        email=user_in.email,
        username=user_in.username,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        institution_id=user_in.institution_id,
        department=user_in.department,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"New user registered: {user.email}")
    return user


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login and get JWT tokens."""
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid email or password", "code": "INVALID_CREDENTIALS"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail={"message": "Account disabled", "code": "ACCOUNT_DISABLED"})

    token_data = {"sub": user.id, "email": user.email, "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Store refresh token hash
    user.refresh_token = refresh_token
    user.last_login_at = datetime.utcnow()
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail={"message": "Invalid refresh token", "code": "INVALID_TOKEN"})

    result = await db.execute(select(User).where(User.id == payload.get("sub")))
    user = result.scalar_one_or_none()

    if not user or user.refresh_token != request.refresh_token:
        raise HTTPException(status_code=401, detail={"message": "Token revoked", "code": "TOKEN_REVOKED"})

    token_data = {"sub": user.id, "email": user.email, "role": user.role}
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    user.refresh_token = new_refresh_token
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Logout - invalidate refresh token."""
    current_user.refresh_token = None
    await db.commit()
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return current_user


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail={"message": "Current password is incorrect", "code": "WRONG_PASSWORD"})

    current_user.hashed_password = hash_password(request.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}