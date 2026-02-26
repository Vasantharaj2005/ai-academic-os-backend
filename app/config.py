"""
Configuration management for the AI Academic OS backend.
Loads environment variables and provides typed configuration.
"""

from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field
from typing import Optional, List
from enum import Enum
import logging
import os

_config_logger = logging.getLogger(__name__)

# Known-weak values that must never be used in production
_WEAK_SECRET_KEYS = {
    "dev-secret-key-change-in-prod",
    "secret",
    "changeme",
    "CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_HEX_64",
    "your-secret-key",
}
_WEAK_DB_PASSWORDS = {
    "", "postgres", "password", "12345", "123456", "admin",
    "test", "changeme", "CHANGE_ME_STRONG_PASSWORD_HERE",
}


class EnvironmentType(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProviderType(str, Enum):
    AUTO = "auto"          # pick the first key that is configured
    GROQ = "groq"
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "AI Academic OS"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: EnvironmentType = EnvironmentType.DEVELOPMENT
    DEBUG: bool = False
    LOG_LEVEL: LogLevel = LogLevel.INFO
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]

    # LLM Provider Selection
    # Options: auto | groq | gemini | openai | anthropic | mock
    # auto = uses first key that is set (priority: groq → gemini → openai → anthropic)
    PRIMARY_PROVIDER: ProviderType = ProviderType.AUTO

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Security
    SECRET_KEY: str = Field("dev-secret-key-change-in-prod", alias="SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = Field("postgres", alias="POSTGRES_PASSWORD")
    POSTGRES_DB: str = "ai_academic_os"
    DATABASE_URL: Optional[str] = None

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = "ai-academic-os"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(None, alias="OPENAI_API_KEY")
    OPENAI_ORG_ID: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"

    # Anthropic
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-opus-20240229"

    # Google Gemini (new google-genai SDK)
    GOOGLE_API_KEY: Optional[str] = Field(None, alias="GOOGLE_API_KEY")
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"

    # Groq
    GROQ_API_KEY: Optional[str] = Field(None, alias="GROQ_API_KEY")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Local LLM
    LLAMA_MODEL_PATH: Optional[str] = None
    USE_LOCAL_LLM: bool = False

    # Pinecone
    PINECONE_API_KEY: Optional[str] = Field(None, alias="PINECONE_API_KEY")
    PINECONE_ENVIRONMENT: str = "gcp-starter"
    PINECONE_INDEX_NAME: str = "academic-memory"
    PINECONE_DIMENSION: int = 1536

    # RAG Configuration
    RAG_CHUNK_SIZE: int = 512
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 10

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 1000
    RATE_LIMIT_PERIOD: int = 60

    # Generation Timeouts
    COURSE_GENERATION_TIMEOUT: int = 600
    AGENT_TIMEOUT: int = 120

    # File Upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".pptx", ".xlsx"]

    def model_post_init(self, __context):
        # ── SEC-002: Reject known-weak JWT secret keys ──────────────────────
        if self.SECRET_KEY in _WEAK_SECRET_KEYS:
            if self.ENVIRONMENT == EnvironmentType.PRODUCTION:
                raise ValueError(
                    "FATAL: SECRET_KEY is a known-weak placeholder. "
                    "Generate a strong key with: "
                    "python -c \"import secrets; print(secrets.token_hex(64))\""
                )
            else:
                _config_logger.warning(
                    "⚠️  SECRET_KEY is a known-weak placeholder. "
                    "Update it before deploying to production!"
                )

        # ── SEC-003: Reject trivially weak database passwords ───────────────
        if self.POSTGRES_PASSWORD in _WEAK_DB_PASSWORDS:
            if self.ENVIRONMENT == EnvironmentType.PRODUCTION:
                raise ValueError(
                    "FATAL: POSTGRES_PASSWORD is too weak for production. "
                    "Generate a strong password with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            else:
                _config_logger.warning(
                    "⚠️  POSTGRES_PASSWORD is weak. Set a strong password before deploying!"
                )

        # ── SEC-011: Warn if DEBUG is enabled outside development ───────────
        if self.DEBUG and self.ENVIRONMENT != EnvironmentType.DEVELOPMENT:
            _config_logger.warning(
                "⚠️  DEBUG=True is enabled in a non-development environment. "
                "This disables TrustedHostMiddleware and may leak tracebacks!"
            )

        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        if not self.REDIS_URL:
            if self.REDIS_PASSWORD:
                self.REDIS_URL = f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            else:
                self.REDIS_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
            self.CELERY_RESULT_BACKEND = self.REDIS_URL

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()