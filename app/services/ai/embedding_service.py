"""
Embedding Service — generates vector embeddings.
Uses new google-genai SDK (google-genai>=1.0) when GOOGLE_API_KEY is set.
Priority: Gemini → OpenAI → zero-vectors (dev fallback)
"""

import asyncio
import logging
from typing import List

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Standalone embedding service used by RAGService.
    Provider priority: Gemini → OpenAI → zero-vectors (dev fallback).
    """

    def __init__(self):
        self._gemini_client = None   # google.genai.Client
        self._openai_client = None
        self._dimension: int = settings.PINECONE_DIMENSION

    async def initialize(self):
        """Initialise embedding clients."""
        if settings.GOOGLE_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
                # Gemini text-embedding-004 produces 768-dim vectors
                self._dimension = 768
                logger.info(
                    f"EmbeddingService: Gemini ready "
                    f"(model: {settings.GEMINI_EMBEDDING_MODEL}, dim: {self._dimension})"
                )
            except ImportError:
                logger.error(
                    "google-genai not installed. "
                    "Run: uv pip install google-genai>=1.0.0"
                )
            except Exception as e:
                logger.error(f"EmbeddingService: Gemini init failed: {e}")

        if settings.OPENAI_API_KEY and self._gemini_client is None:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                self._dimension = settings.PINECONE_DIMENSION
                logger.info("EmbeddingService: OpenAI embeddings ready")
            except Exception as e:
                logger.error(f"EmbeddingService: OpenAI init failed: {e}")

        if self._gemini_client is None and self._openai_client is None:
            logger.warning(
                "EmbeddingService: No embedding provider available. "
                "Using zero-vectors (set GOOGLE_API_KEY to enable real embeddings)."
            )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of document texts."""
        if not texts:
            return []

        if self._gemini_client:
            return await self._embed_gemini(texts, task_type="RETRIEVAL_DOCUMENT")
        if self._openai_client:
            return await self._embed_openai(texts)
        return [[0.0] * self._dimension for _ in texts]

    async def embed_query(self, query: str) -> List[float]:
        """Embed a single query string."""
        if self._gemini_client:
            results = await self._embed_gemini([query], task_type="RETRIEVAL_QUERY")
            return results[0]
        vectors = await self.embed([query])
        return vectors[0]

    # ── Providers ──────────────────────────────────────────────────────────────

    async def _embed_gemini(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """Embed using google-genai SDK — new Client API."""
        from google.genai import types

        loop = asyncio.get_event_loop()

        def _call():
            results = []
            for text in texts:
                res = self._gemini_client.models.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(task_type=task_type),
                )
                results.append(res.embeddings[0].values)
            return results

        try:
            return await loop.run_in_executor(None, _call)
        except Exception as e:
            logger.error(f"Gemini embed_content failed: {e}")
            return [[0.0] * self._dimension for _ in texts]

    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        try:
            response = await self._openai_client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            return [[0.0] * self._dimension for _ in texts]

    @property
    def dimension(self) -> int:
        return self._dimension

    def provider_name(self) -> str:
        if self._gemini_client:
            return "gemini"
        if self._openai_client:
            return "openai"
        return "zeros (dev)"

    async def close(self):
        pass


# Singleton
embedding_service = EmbeddingService()
