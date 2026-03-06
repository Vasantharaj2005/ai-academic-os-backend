"""
RAG (Retrieval-Augmented Generation) Service.
Handles document ingestion and semantic retrieval via Pinecone.
"""

import logging
import hashlib
from typing import List, Dict, Any, Optional

from app.config import settings
from app.services.ai.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class RAGService:
    """
    RAG service that indexes documents in Pinecone and retrieves
    relevant context to augment LLM prompts.
    """

    def __init__(self):
        self._index = None

    async def initialize(self):
        """Initialize Pinecone connection."""
        # Initialize the embedding service first
        await embedding_service.initialize()

        if not settings.PINECONE_API_KEY:
            logger.warning("Pinecone not configured - RAG disabled (set PINECONE_API_KEY to enable)")
            return

        try:
            from pinecone import Pinecone, ServerlessSpec

            pc = Pinecone(api_key=settings.PINECONE_API_KEY)

            # Check if index exists (handles v3 response object)
            existing_indexes = [i.name if hasattr(i, "name") else i for i in pc.list_indexes()]

            if settings.PINECONE_INDEX_NAME not in existing_indexes:
                pc.create_index(
                    name=settings.PINECONE_INDEX_NAME,
                    dimension=settings.PINECONE_DIMENSION,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
                logger.info(f"Created Pinecone index: {settings.PINECONE_INDEX_NAME}")

            self._index = pc.Index(settings.PINECONE_INDEX_NAME)
            logger.info("RAG service initialized with Pinecone")
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}")

    async def ingest_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Ingest a document into the vector store.
        Splits into chunks and stores embeddings.
        """
        if not self._index:
            return "rag-disabled"

        # Chunk the document
        chunks = self._chunk_text(text, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
        vectors = []

        embeddings = await embedding_service.embed(chunks)

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = doc_id or hashlib.md5(chunk.encode()).hexdigest()
            chunk_id = f"{chunk_id}-{i}"
            vectors.append({
                "id": chunk_id,
                "values": embedding,
                "metadata": {**metadata, "text": chunk[:1000], "chunk_index": i},
            })

        self._index.upsert(vectors=vectors)
        logger.info(f"Ingested {len(vectors)} chunks for document")
        return doc_id or chunks[0][:16]

    async def retrieve(
        self,
        query: str,
        institution_id: Optional[str] = None,
        top_k: int = None,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents for a query.
        """
        if not self._index:
            return []

        top_k = top_k or settings.RAG_TOP_K

        query_vector = await embedding_service.embed_query(query)

        filter_dict = {}
        if institution_id:
            filter_dict["institution_id"] = institution_id
        if filter_metadata:
            filter_dict.update(filter_metadata)

        results = self._index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            filter=filter_dict if filter_dict else None,
        )

        documents = []
        for match in results.matches:
            if match.score >= 0.7:  # Relevance threshold
                documents.append({
                    "id": match.id,
                    "content": match.metadata.get("text", ""),
                    "score": match.score,
                    "metadata": match.metadata,
                })

        logger.debug(f"RAG retrieved {len(documents)} relevant docs for query")
        return documents

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i: i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks if chunks else [text]

    async def close(self):
        pass


# Singleton
rag_service = RAGService()