"""Rate limiting middleware using Redis sliding window with in-memory fallback."""

import time
import logging
from collections import defaultdict
from threading import Lock
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Public paths excluded from rate limiting
EXCLUDED_PATHS = {"/health", "/api/v1/health", "/", "/api/docs", "/api/redoc", "/openapi.json"}

# ── SEC-006: In-memory fallback rate limiter (used when Redis is unavailable) ──
_fallback_lock = Lock()
_fallback_store: dict[str, list[float]] = defaultdict(list)


def _in_memory_rate_check(key: str, limit: int, window: int) -> bool:
    """Return True if the request should be allowed, False if rate limit exceeded."""
    now = time.time()
    cutoff = now - window
    with _fallback_lock:
        timestamps = _fallback_store[key]
        # Prune old entries
        _fallback_store[key] = [t for t in timestamps if t > cutoff]
        if len(_fallback_store[key]) >= limit:
            return False
        _fallback_store[key].append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_ip}"

        try:
            from app.core.memory import shared_memory
            now = time.time()

            # Increment and check using Redis
            count = await shared_memory.client.incr(key)
            if count == 1:
                await shared_memory.client.expire(key, settings.RATE_LIMIT_PERIOD)

            if count > settings.RATE_LIMIT_REQUESTS:
                return JSONResponse(
                    status_code=429,
                    content={"message": "Rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED"},
                    headers={"Retry-After": str(settings.RATE_LIMIT_PERIOD)},
                )

        except Exception as e:
            # SEC-006: Redis unavailable — use in-memory fallback instead of failing open
            logger.warning(f"Rate limiter Redis unavailable, using in-memory fallback: {e}")
            allowed = _in_memory_rate_check(key, settings.RATE_LIMIT_REQUESTS, settings.RATE_LIMIT_PERIOD)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"message": "Rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED"},
                    headers={"Retry-After": str(settings.RATE_LIMIT_PERIOD)},
                )

        return await call_next(request)