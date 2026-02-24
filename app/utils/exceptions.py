"""Custom application exceptions."""

from fastapi import HTTPException
from typing import Optional, Any


class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, code: str = "APP_ERROR", details: Optional[Any] = None):
        self.message = message
        self.code = code
        self.details = details
        super().__init__(message)


class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR")


class AuthorizationError(AppException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "AUTHZ_ERROR")


class NotFoundError(AppException):
    def __init__(self, resource: str, resource_id: Any = None):
        msg = f"{resource} not found" + (f": {resource_id}" if resource_id else "")
        super().__init__(msg, "NOT_FOUND")


class ValidationError(AppException):
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message, "VALIDATION_ERROR", {"field": field})


class AgentError(AppException):
    def __init__(self, agent_name: str, message: str):
        super().__init__(f"Agent {agent_name} failed: {message}", "AGENT_ERROR")


class LLMError(AppException):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message, "LLM_ERROR", {"provider": provider})


class StorageError(AppException):
    def __init__(self, message: str):
        super().__init__(message, "STORAGE_ERROR")


class RateLimitError(AppException):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "RATE_LIMIT_ERROR")


class GenerationError(AppException):
    def __init__(self, message: str, workflow_id: Optional[str] = None):
        super().__init__(message, "GENERATION_ERROR", {"workflow_id": workflow_id})


def http_exception(status_code: int, message: str, code: str = "ERROR") -> HTTPException:
    """Create a standardized HTTP exception."""
    return HTTPException(
        status_code=status_code,
        detail={"message": message, "code": code}
    )