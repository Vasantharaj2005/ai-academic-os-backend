"""
Main FastAPI application entry point.
AI Academic Operating System Backend.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from app.config import settings
from app.api.routes import auth, courses, generation, agents, assessments, compliance, analytics, health, validation
from app.api.routes import export as export_routes
from app.api.routes import question_paper as qp_routes
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.core.orchestrator import orchestrator
from app.utils.logger import setup_logging
from app.utils.metrics import setup_metrics

# Setup logging first
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("Starting AI Academic OS backend...")

    # Initialize database tables
    try:
        from app.services.database.session import create_tables
        
        # Import models to ensure they are registered with SQLAlchemy
        # This prevents "failed to locate a name" errors for string relationships
        from app.models.database.user import User
        from app.models.database.course import Course
        from app.models.database.syllabus import Syllabus
        from app.models.database.assessment import Assessment
        from app.models.database.compliance import Compliance
        
        await create_tables()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # Initialize agent orchestrator (lazy - only connects services)
    try:
        await orchestrator.initialize()
        app.state.orchestrator = orchestrator
        logger.info("Agent Orchestrator ready")
    except Exception as e:
        logger.error(f"Orchestrator initialization failed (will retry on first use): {e}")

    setup_metrics()
    logger.info("AI Academic OS backend started successfully")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down...")
    try:
        await orchestrator.close()
    except Exception:
        pass
    logger.info("Shutdown complete")


# ── Application ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Academic Operating System API",
    description="""
## 🎓 AI Academic Operating System

A multi-agent AI platform that autonomously generates complete academic course packages.

### Features
- **Multi-Agent Pipeline**: 6 specialized AI agents working in coordination
- **Curriculum Generation**: Full syllabus with CLOs aligned to Bloom's taxonomy
- **Semester Planning**: 16-week teaching plan with assessment schedule
- **Content Generation**: Lecture notes and slide deck outlines per module
- **Assessment Design**: Quiz, midterm, final papers + question bank
- **OBE Compliance**: CO-PO mapping for NBA/NAAC accreditation
- **Analytics**: Student performance prediction and teaching insights

### Authentication
Use `POST /api/v1/auth/login` to get your JWT token, then include it as:
```
Authorization: Bearer <your-token>
```
    """,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    # SEC-017: Hide interactive docs AND raw schema in production
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/api/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
# SEC-007: Explicit methods and headers instead of wildcard "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

# SEC-011: Always apply TrustedHostMiddleware; DEBUG flag no longer bypasses it
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)


@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start:.4f}s"
    # SEC-012: Add standard security response headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


# ── Global Exception Handlers ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# ── Routers ────────────────────────────────────────────────────────────────────
PREFIX = settings.API_PREFIX

app.include_router(auth.router, prefix=f"{PREFIX}/auth", tags=["🔐 Authentication"])
app.include_router(courses.router, prefix=f"{PREFIX}/courses", tags=["📚 Courses"])
app.include_router(generation.router, prefix=f"{PREFIX}/courses", tags=["🤖 Generation"])
app.include_router(agents.router, prefix=f"{PREFIX}/agents", tags=["🧠 Agents"])
app.include_router(assessments.router, prefix=f"{PREFIX}/courses", tags=["📝 Assessments"])
app.include_router(compliance.router, prefix=f"{PREFIX}/courses", tags=["✅ OBE Compliance"])
app.include_router(analytics.router, prefix=f"{PREFIX}/courses", tags=["📊 Analytics"])
app.include_router(validation.router, prefix=f"{PREFIX}/courses", tags=["🛡️ Validation"])
app.include_router(export_routes.router, prefix=f"{PREFIX}/courses",        tags=["📄 PDF Export"])
app.include_router(qp_routes.router,    prefix=f"{PREFIX}/question-papers", tags=["📝 Question Papers"])
app.include_router(health.router,       prefix=f"{PREFIX}/health",          tags=["❤️ Health"])



# ── Root ───────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "operational",
        "docs": "/api/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )