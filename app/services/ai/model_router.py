"""
Model Router — selects the optimal LLM model/provider for a given task type.
Supports Groq, Gemini, OpenAI, Anthropic.
Set PRIMARY_PROVIDER in .env to override automatic selection.
"""

import logging
from typing import Dict, Optional, Tuple

from app.config import settings, ProviderType

logger = logging.getLogger(__name__)

# ── Task-to-model profiles ─────────────────────────────────────────────────────
# Each task maps to an ordered list of (provider, model, temperature, max_tokens).
# First available provider wins.
TASK_PROFILES: Dict[str, list] = {
    # Curriculum — precise JSON, low temperature
    "curriculum": [
        ("groq",      "llama-3.3-70b-versatile",   0.2, 8000),
        ("gemini",    "gemini-2.0-flash",            0.2, 8192),
        ("openai",    "gpt-4-turbo-preview",         0.2, 4096),
        ("anthropic", "claude-3-opus-20240229",      0.2, 4096),
    ],
    # Semester planning
    "semester": [
        ("groq",      "llama-3.3-70b-versatile",   0.3, 6000),
        ("gemini",    "gemini-2.0-flash",            0.3, 4096),
        ("openai",    "gpt-4-turbo-preview",         0.3, 4096),
        ("anthropic", "claude-3-haiku-20240307",     0.3, 4096),
    ],
    # Content / lecture notes — creative, longer
    "content": [
        ("groq",      "llama-3.3-70b-versatile",   0.7, 8000),
        ("gemini",    "gemini-2.0-flash",            0.7, 8192),
        ("openai",    "gpt-4-turbo-preview",         0.7, 4096),
        ("anthropic", "claude-3-sonnet-20240229",    0.7, 4096),
    ],
    # Assessment — structured JSON
    "assessment": [
        ("groq",      "llama-3.3-70b-versatile",   0.3, 7000),
        ("gemini",    "gemini-2.0-flash",            0.3, 6144),
        ("openai",    "gpt-4-turbo-preview",         0.3, 4096),
        ("anthropic", "claude-3-opus-20240229",      0.3, 4096),
    ],
    # OBE mapping — very structured, lowest temperature
    "obe": [
        ("groq",      "llama-3.3-70b-versatile",   0.1, 4000),
        ("gemini",    "gemini-2.0-flash",            0.1, 4096),
        ("openai",    "gpt-4-turbo-preview",         0.1, 4096),
        ("anthropic", "claude-3-haiku-20240307",     0.1, 4096),
    ],
    # Analytics / insights
    "analytics": [
        ("groq",      "llama-3.3-70b-versatile",   0.4, 4000),
        ("gemini",    "gemini-2.0-flash",            0.4, 4096),
        ("openai",    "gpt-4-turbo-preview",         0.4, 4096),
        ("anthropic", "claude-3-sonnet-20240229",    0.4, 4096),
    ],
    # Default fallback
    "default": [
        ("groq",      "llama-3.3-70b-versatile",   0.7, 2048),
        ("gemini",    "gemini-2.0-flash",            0.7, 2048),
        ("openai",    "gpt-4-turbo-preview",         0.7, 2048),
        ("anthropic", "claude-3-haiku-20240307",     0.7, 2048),
    ],
}


class ModelRouter:
    """
    Selects the best available (provider, model) pair for a task.
    Respects PRIMARY_PROVIDER setting; falls back automatically.
    """

    def __init__(self):
        self._available: Dict[str, bool] = {
            "groq":      bool(settings.GROQ_API_KEY),
            "gemini":    bool(settings.GOOGLE_API_KEY),
            "openai":    bool(settings.OPENAI_API_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
        }
        self._primary = settings.PRIMARY_PROVIDER.value  # str e.g. "groq"
        logger.info(
            "ModelRouter: "
            + ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in self._available.items())
            + f" | PRIMARY_PROVIDER={self._primary}"
        )

    def route(
        self,
        task: str = "default",
        override_provider: Optional[str] = None,
        override_model: Optional[str] = None,
    ) -> Tuple[str, str, float, int]:
        """
        Returns (provider, model, temperature, max_tokens) for the given task.

        Priority:
          1. override_provider (per-call explicit override)
          2. PRIMARY_PROVIDER env setting  (if not "auto")
          3. First available provider from TASK_PROFILES
        """
        profiles = TASK_PROFILES.get(task, TASK_PROFILES["default"])

        # Determine forced provider (override > PRIMARY_PROVIDER > auto)
        force = override_provider
        if not force and self._primary not in ("auto", "mock"):
            force = self._primary

        for provider, model, temperature, max_tokens in profiles:
            if force and provider != force:
                continue
            if self._available.get(provider, False):
                final_model = override_model or model
                logger.debug(f"ModelRouter: task={task} → {provider}/{final_model}")
                return provider, final_model, temperature, max_tokens

        # If forced provider not available, fall back to any available
        if force:
            logger.warning(
                f"Forced provider '{force}' not available for task '{task}'. "
                "Falling back to auto-select."
            )
            for provider, model, temperature, max_tokens in profiles:
                if self._available.get(provider, False):
                    return provider, override_model or model, temperature, max_tokens

        logger.warning(f"No provider available for task '{task}'. Using mock.")
        return "mock", "none", 0.7, 2048

    def get_primary_provider(self) -> str:
        if self._primary not in ("auto", "mock"):
            return self._primary
        for p in ("groq", "gemini", "openai", "anthropic"):
            if self._available.get(p):
                return p
        return "mock"

    def get_available_providers(self) -> Dict[str, bool]:
        return dict(self._available)

    def update_availability(self, provider: str, available: bool):
        self._available[provider] = available
        logger.info(f"ModelRouter: '{provider}' availability → {available}")


# Singleton
model_router = ModelRouter()
