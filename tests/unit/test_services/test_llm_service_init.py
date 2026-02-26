import importlib.util
import pytest

from app.config import settings, ProviderType
from app.services.ai.llm_service import LLMService


@pytest.mark.asyncio
async def test_llm_initialize_groq_missing_falls_back_to_gemini(caplog, monkeypatch):
    if importlib.util.find_spec("groq") is not None:
        pytest.skip("groq is installed; this test targets the missing-module fallback")
    if importlib.util.find_spec("google.genai") is None:
        pytest.skip("google-genai not installed; cannot test gemini fallback")

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key", raising=False)
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "test-google-key", raising=False)
    monkeypatch.setattr(settings, "PRIMARY_PROVIDER", ProviderType.AUTO, raising=False)

    service = LLMService()
    await service.initialize()

    assert service.primary_provider == "gemini"
    assert service._gemini_client is not None
    assert any("Groq init failed" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_llm_initialize_no_keys_uses_mock(caplog, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "PRIMARY_PROVIDER", ProviderType.AUTO, raising=False)

    service = LLMService()
    await service.initialize()

    assert service.primary_provider == "mock"
    assert any("No LLM provider configured" in rec.message for rec in caplog.records)
