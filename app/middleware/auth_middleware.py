"""Auth middleware - minimal version (JWT handled in route dependencies)."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Lightweight auth middleware that extracts token info for logging.
    Full auth is handled in route-level dependencies via get_current_user.
    """

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from app.services.auth.auth_service import decode_token
            token = auth_header[7:]
            payload = decode_token(token)
            if payload:
                request.state.user_id = payload.get("sub")
                request.state.user_role = payload.get("role")
        return await call_next(request)