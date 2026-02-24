"""Rate limiting middleware using Redis sliding window."""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Public paths excluded from rate limiting
EXCLUDED_PATHS = {"/health", "/api/v1/health", "/", "/api/docs", "/api/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        try:
            from app.core.memory import shared_memory
            client_ip = request.client.host if request.client else "unknown"
            key = f"rate_limit:{client_ip}"
            now = time.time()
            window_start = now - settings.RATE_LIMIT_PERIOD

            # Increment and check
            count = await shared_memory.client.incr(key)
            if count == 1:
                await shared_memory.client.expire(key, settings.RATE_LIMIT_PERIOD)

            if count > settings.RATE_LIMIT_REQUESTS:
                return JSONResponse(
                    status_code=429,
                    content={"message": "Rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED"},
                    headers={"Retry-After": str(settings.RATE_LIMIT_PERIOD)},
                )
        except Exception:
            # If rate limiting fails, don't block the request
            pass

        return await call_next(request)