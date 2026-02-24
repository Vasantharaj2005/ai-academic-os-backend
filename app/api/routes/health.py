"""Health check routes."""

from fastapi import APIRouter
import time
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/")
async def health():
    return {"status": "healthy", "timestamp": time.time()}


@router.get("/detailed")
async def detailed_health():
    """Detailed health check with dependency status."""
    checks = {}

    # Check Redis
    try:
        from app.core.memory import shared_memory
        await shared_memory.client.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {e}"

    # Check DB
    try:
        from app.services.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {e}"

    overall = "healthy" if all("healthy" == v for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "timestamp": time.time()}