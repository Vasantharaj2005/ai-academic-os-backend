"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import logging

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.schemas.auth import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    TokenResponse,
    RefreshTokenRequest,
    PasswordChangeRequest,
)
from app.services.auth.auth_service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    hash_refresh_token, decode_token,
)
from app.api.dependencies.auth_deps import get_current_active_user
from app.utils.helpers import generate_uuid
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# ── SEC-004: Login brute-force protection constants ────────────────────────────
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300  # 5 minutes lock window


async def _check_login_rate_limit(client_ip: str, email: str) -> None:
    """Raise HTTP 429 if the caller has exceeded login attempt threshold."""
    try:
        from app.core.memory import shared_memory
        key = f"login_fail:{client_ip}:{email}"
        count = await shared_memory.client.incr(key)
        if count == 1:
            await shared_memory.client.expire(key, _LOGIN_WINDOW_SECONDS)
        if count > _MAX_LOGIN_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"Too many failed login attempts. Try again in {_LOGIN_WINDOW_SECONDS // 60} minutes.",
                    "code": "TOO_MANY_ATTEMPTS",
                },
                headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)},
            )
    except HTTPException:
        raise
    except Exception:
        # Fail open — if Redis is unavailable don't block the request,
        # but log so the operator knows rate limiting is degraded.
        logger.warning("Login rate-limit check failed (Redis unavailable?); proceeding without guard.")


async def _reset_login_rate_limit(client_ip: str, email: str) -> None:
    """Clear the failed-attempt counter after a successful login."""
    try:
        from app.core.memory import shared_memory
        await shared_memory.client.delete(f"login_fail:{client_ip}:{email}")
    except Exception:
        pass


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
async def login(credentials: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    """Login and get JWT tokens."""
    # SEC-004: Check per-IP + per-email failed attempt count before querying
    client_ip = request.client.host if request.client else "unknown"
    await _check_login_rate_limit(client_ip, credentials.email)

    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        # Increment failure counter only on bad credentials (not on other errors)
        try:
            from app.core.memory import shared_memory
            key = f"login_fail:{client_ip}:{credentials.email}"
            count = await shared_memory.client.incr(key)
            if count == 1:
                await shared_memory.client.expire(key, _LOGIN_WINDOW_SECONDS)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid email or password", "code": "INVALID_CREDENTIALS"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail={"message": "Account disabled", "code": "ACCOUNT_DISABLED"})

    # Successful login — clear fail counter
    await _reset_login_rate_limit(client_ip, credentials.email)

    token_data = {"sub": user.id, "email": user.email, "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # SEC-005: Store hashed refresh token, NOT the raw token
    user.refresh_token = hash_refresh_token(refresh_token)
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

    # SEC-005: Compare stored hash against hash of the submitted token
    if not user or user.refresh_token != hash_refresh_token(request.refresh_token):
        raise HTTPException(status_code=401, detail={"message": "Token revoked", "code": "TOKEN_REVOKED"})

    token_data = {"sub": user.id, "email": user.email, "role": user.role}
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    # SEC-005: Store hash of the new refresh token
    user.refresh_token = hash_refresh_token(new_refresh_token)
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


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile details."""
    updates = payload.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] != current_user.email:
        result = await db.execute(
            select(User).where(User.email == updates["email"], User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail={"message": "Email already registered", "code": "EMAIL_EXISTS"},
            )

    if "username" in updates and updates["username"] != current_user.username:
        result = await db.execute(
            select(User).where(User.username == updates["username"], User.id != current_user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail={"message": "Username already taken", "code": "USERNAME_EXISTS"},
            )

    for field, value in updates.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)
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
    # SEC-016: Invalidate all existing sessions when password changes
    current_user.refresh_token = None
    await db.commit()
    return {"message": "Password changed successfully. Please log in again."}
