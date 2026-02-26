"""Logging configuration for the application."""

import logging
import logging.config
import sys
from typing import Dict, Any

from app.config import settings


class ColorFormatter(logging.Formatter):
    """Formatter that colorizes log levels for terminal output."""

    RESET = "\x1b[0m"
    COLORS = {
        "DEBUG": "\x1b[36m",      # Cyan
        "INFO": "\x1b[32m",       # Green
        "WARNING": "\x1b[33m",    # Yellow
        "ERROR": "\x1b[31m",      # Red
        "CRITICAL": "\x1b[1;31m", # Bold red
    }

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        color = self.COLORS.get(original_levelname, "")
        if color:
            record.levelname = f"{color}{original_levelname}{self.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


def setup_logging() -> None:
    """Configure structured logging for the application."""

    log_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s %(name)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "color": {
                "()": ColorFormatter,
                "format": "[%(asctime)s] %(levelname)s %(name)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter"
                if settings.ENVIRONMENT == "production"
                else None,
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "color",
                "level": settings.LOG_LEVEL.value,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/app.log",
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "formatter": "default",
                "level": settings.LOG_LEVEL.value,
            },
        },
        "root": {
            "level": settings.LOG_LEVEL.value,
            "handlers": ["console", "file"],
        },
        "loggers": {
            "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "sqlalchemy.engine": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "celery": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        },
    }

    # Remove JSON formatter config if not a real class
    if log_config["formatters"]["json"].get("()") is None:
        log_config["formatters"].pop("json")

    logging.config.dictConfig(log_config)
    logging.getLogger(__name__).info(
        f"Logging configured at level {settings.LOG_LEVEL.value}"
    )
