"""
LLM Service — unified interface for Groq, Google Gemini, OpenAI, and Anthropic.
Provider priority (auto mode): Groq → Gemini → OpenAI → Anthropic → Mock
Set PRIMARY_PROVIDER in .env to force a specific provider.
"""

import logging
import time
import asyncio
from typing import Optional, List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings, ProviderType
from app.utils.exceptions import LLMError
from app.utils.metrics import llm_calls_total, llm_tokens_total

logger = logging.getLogger(__name__)

# Auto-detect priority order
AUTO_PRIORITY = [
    (ProviderType.GROQ,      lambda: settings.GROQ_API_KEY),
    (ProviderType.GEMINI,    lambda: settings.GOOGLE_API_KEY),
    (ProviderType.OPENAI,    lambda: settings.OPENAI_API_KEY),
    (ProviderType.ANTHROPIC, lambda: settings.ANTHROPIC_API_KEY),
]


class LLMService:
    """
    Unified LLM service. Supports Groq, Gemini, OpenAI, Anthropic.
    Control via PRIMARY_PROVIDER env var (auto/groq/gemini/openai/anthropic/mock).
    """

    def __init__(self):
        self._groq_client = None        # groq.AsyncGroq
        self._gemini_client = None      # google.genai.Client
        self._openai_client = None      # openai.AsyncOpenAI
        self._anthropic_client = None   # anthropic.AsyncAnthropic
        self.primary_provider = "mock"

    async def initialize(self):
        """Initialize all configured LLM clients."""

        # ── Groq ──────────────────────────────────────────────────────────────
        if settings.GROQ_API_KEY:
            try:
                from groq import AsyncGroq
                self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
                logger.info(f"Groq client initialised (model: {settings.GROQ_MODEL})")
            except Exception as e:
                logger.error(f"Groq init failed: {e}")

        # ── Google Gemini (new google-genai SDK) ──────────────────────────────
        if settings.GOOGLE_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                logger.info(f"Gemini client initialised (model: {settings.GEMINI_MODEL})")
            except ImportError:
                logger.error("google-genai not installed. Run: uv pip install google-genai>=1.0.0")
            except Exception as e:
                logger.error(f"Gemini init failed: {e}")

        # ── OpenAI ────────────────────────────────────────────────────────────
        if settings.OPENAI_API_KEY:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    organization=settings.OPENAI_ORG_ID,
                )
                logger.info("OpenAI client initialised")
            except Exception as e:
                logger.error(f"OpenAI init failed: {e}")

        # ── Anthropic ─────────────────────────────────────────────────────────
        if settings.ANTHROPIC_API_KEY:
            try:
                import anthropic
                self._anthropic_client = anthropic.AsyncAnthropic(
                    api_key=settings.ANTHROPIC_API_KEY
                )
                logger.info("Anthropic client initialised")
            except Exception as e:
                logger.error(f"Anthropic init failed: {e}")

        # ── Select primary provider ────────────────────────────────────────────
        self.primary_provider = self._resolve_primary_provider()
        logger.info(f"Primary LLM provider: {self.primary_provider}")

        if self.primary_provider == "mock":
            logger.warning(
                "⚠️  No LLM provider configured. "
                "Set GROQ_API_KEY or GOOGLE_API_KEY in .env to enable real AI."
            )

    def _resolve_primary_provider(self) -> str:
        """Resolve which provider to use based on PRIMARY_PROVIDER setting."""
        cfg = settings.PRIMARY_PROVIDER

        if cfg != ProviderType.AUTO:
            # Explicit override — validate it's actually initialised
            client_map = {
                ProviderType.GROQ:      self._groq_client,
                ProviderType.GEMINI:    self._gemini_client,
                ProviderType.OPENAI:    self._openai_client,
                ProviderType.ANTHROPIC: self._anthropic_client,
                ProviderType.MOCK:      True,
            }
            if client_map.get(cfg):
                return cfg.value
            logger.warning(
                f"PRIMARY_PROVIDER={cfg.value} is set but that provider failed to init "
                f"(is the API key set?). Falling back to auto."
            )

        # Auto: pick first configured provider
        for provider, key_fn in AUTO_PRIORITY:
            client = {
                ProviderType.GROQ:      self._groq_client,
                ProviderType.GEMINI:    self._gemini_client,
                ProviderType.OPENAI:    self._openai_client,
                ProviderType.ANTHROPIC: self._anthropic_client,
            }.get(provider)
            if client:
                return provider.value

        return "mock"

    # ── Public generate API ───────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        response_format: Optional[str] = None,  # "json"
    ) -> str:
        """
        Generate text using the active LLM provider.
        Cascades: primary → remaining providers → mock.
        Pass `provider='groq'` etc. to override for a single call.
        """
        selected = provider or self.primary_provider

        # Build ordered list of providers to try
        fallback_chain = self._build_fallback_chain(selected)

        last_exc = None
        for p in fallback_chain:
            try:
                return await self._call_provider(p, prompt, system_message, temperature, max_tokens, model, response_format)
            except Exception as e:
                last_exc = e
                logger.warning(f"Provider '{p}' failed: {e}. Trying next...")

        # All providers failed — fall back to mock
        logger.error(f"All providers failed. Last error: {last_exc}")
        return self._generate_mock(prompt)

    def _build_fallback_chain(self, primary: str) -> List[str]:
        """Return ordered list starting with primary, then others, no repeats."""
        all_providers = []
        if self._groq_client:
            all_providers.append("groq")
        if self._gemini_client:
            all_providers.append("gemini")
        if self._openai_client:
            all_providers.append("openai")
        if self._anthropic_client:
            all_providers.append("anthropic")

        if not all_providers:
            return ["mock"]

        # Put primary first
        chain = [primary] if primary in all_providers else []
        chain += [p for p in all_providers if p != primary]
        return chain or ["mock"]

    async def _call_provider(
        self, provider: str, prompt: str, system_message: Optional[str],
        temperature: float, max_tokens: int, model: Optional[str],
        response_format: Optional[str],
    ) -> str:
        if provider == "groq":
            return await self._generate_groq(prompt, system_message, temperature, max_tokens, model, response_format)
        elif provider == "gemini":
            return await self._generate_gemini(prompt, system_message, temperature, max_tokens, model, response_format)
        elif provider == "openai":
            return await self._generate_openai(prompt, system_message, temperature, max_tokens, model, response_format)
        elif provider == "anthropic":
            return await self._generate_anthropic(prompt, system_message, temperature, max_tokens, model)
        return self._generate_mock(prompt)

    # ── Provider implementations ──────────────────────────────────────────────

    async def _generate_groq(
        self,
        prompt: str,
        system_message: Optional[str],
        temperature: float,
        max_tokens: int,
        model: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> str:
        model = model or settings.GROQ_MODEL
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        start = time.time()
        response = await self._groq_client.chat.completions.create(**kwargs)
        duration = time.time() - start

        llm_calls_total.labels(provider="groq", model=model, status="success").inc()
        logger.debug(f"Groq call: {response.usage.total_tokens} tokens in {duration:.2f}s")
        return response.choices[0].message.content

    async def _generate_gemini(
        self,
        prompt: str,
        system_message: Optional[str],
        temperature: float,
        max_tokens: int,
        model: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> str:
        from google.genai import types
        model = model or settings.GEMINI_MODEL
        full_prompt = f"{system_message}\n\n{prompt}" if system_message else prompt

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if response_format == "json":
            config.response_mime_type = "application/json"

        start = time.time()
        loop = asyncio.get_event_loop()

        def _call():
            return self._gemini_client.models.generate_content(
                model=model, contents=full_prompt, config=config,
            )

        response = await loop.run_in_executor(None, _call)
        duration = time.time() - start

        llm_calls_total.labels(provider="gemini", model=model, status="success").inc()
        logger.debug(f"Gemini call completed in {duration:.2f}s")
        return response.text

    async def _generate_openai(
        self,
        prompt: str,
        system_message: Optional[str],
        temperature: float,
        max_tokens: int,
        model: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> str:
        model = model or settings.OPENAI_MODEL
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        start = time.time()
        response = await self._openai_client.chat.completions.create(**kwargs)
        duration = time.time() - start

        llm_calls_total.labels(provider="openai", model=model, status="success").inc()
        llm_tokens_total.labels(provider="openai", model=model, type="prompt").inc(response.usage.prompt_tokens)
        llm_tokens_total.labels(provider="openai", model=model, type="completion").inc(response.usage.completion_tokens)
        logger.debug(f"OpenAI call: {response.usage.total_tokens} tokens in {duration:.2f}s")
        return response.choices[0].message.content

    async def _generate_anthropic(
        self,
        prompt: str,
        system_message: Optional[str],
        temperature: float,
        max_tokens: int,
        model: Optional[str] = None,
    ) -> str:
        model = model or settings.ANTHROPIC_MODEL
        kwargs: Dict[str, Any] = dict(
            model=model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system_message:
            kwargs["system"] = system_message

        start = time.time()
        response = await self._anthropic_client.messages.create(**kwargs)
        duration = time.time() - start

        llm_calls_total.labels(provider="anthropic", model=model, status="success").inc()
        logger.debug(f"Anthropic call completed in {duration:.2f}s")
        return response.content[0].text

    def _generate_mock(self, prompt: str) -> str:
        logger.warning("Using mock LLM — set GROQ_API_KEY or GOOGLE_API_KEY in .env")
        return '{"mock": true, "message": "No LLM provider configured. Set GROQ_API_KEY in .env.", "data": []}'

    # ── Embeddings ────────────────────────────────────────────────────────────

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Embeddings: Gemini → OpenAI → zeros (Groq/Anthropic have no embedding API)."""
        if self._gemini_client:
            try:
                loop = asyncio.get_event_loop()

                def _embed():
                    results = []
                    for text in texts:
                        res = self._gemini_client.models.embed_content(
                            model=settings.GEMINI_EMBEDDING_MODEL,
                            contents=text,
                        )
                        results.append(res.embeddings[0].values)
                    return results

                return await loop.run_in_executor(None, _embed)
            except Exception as e:
                logger.warning(f"Gemini embedding failed: {e}")

        if self._openai_client:
            try:
                response = await self._openai_client.embeddings.create(
                    model=settings.OPENAI_EMBEDDING_MODEL, input=texts,
                )
                return [item.embedding for item in response.data]
            except Exception as e:
                logger.warning(f"OpenAI embedding failed: {e}")

        return [[0.0] * settings.PINECONE_DIMENSION for _ in texts]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_primary_provider(self) -> str:
        return self.primary_provider

    def get_available_providers(self) -> Dict[str, bool]:
        return {
            "groq":      self._groq_client is not None,
            "gemini":    self._gemini_client is not None,
            "openai":    self._openai_client is not None,
            "anthropic": self._anthropic_client is not None,
        }

    def get_provider_models(self) -> Dict[str, str]:
        """Return active model name for each configured provider."""
        models = {}
        if self._groq_client:
            models["groq"] = settings.GROQ_MODEL
        if self._gemini_client:
            models["gemini"] = settings.GEMINI_MODEL
        if self._openai_client:
            models["openai"] = settings.OPENAI_MODEL
        if self._anthropic_client:
            models["anthropic"] = settings.ANTHROPIC_MODEL
        return models

    async def close(self):
        pass


# Singleton
llm_service = LLMService()