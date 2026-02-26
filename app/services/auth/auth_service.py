"""Authentication service - JWT tokens and password hashing."""

from datetime import datetime, timedelta
from typing import Optional
import hashlib
from jose import JWTError, jwt
import bcrypt
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    # bcrypt has a 72 byte limit, truncate if necessary to prevent errors
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode('utf-8'))
    except ValueError:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def hash_refresh_token(token: str) -> str:
    """SEC-005: Return SHA-256 hash of the token to store in DB instead of plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Token decode failed: {e}")
        return None