"""
Base agent class all specialized agents inherit from.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import time
from datetime import datetime
import logging

from app.services.ai.llm_service import LLMService
from app.services.ai.rag_service import RAGService
from app.core.memory import SharedMemory


class AgentContext(BaseModel):
    workflow_id: str
    course_id: Optional[str] = None
    user_id: str
    institution_id: str
    input_data: Dict[str, Any]
    shared_memory: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        arbitrary_types_allowed = True


class AgentResult(BaseModel):
    agent_name: str
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    processing_time: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        llm_service: LLMService,
        rag_service: RAGService,
        shared_memory: SharedMemory,
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.llm_service = llm_service
        self.rag_service = rag_service
        self.shared_memory = shared_memory
        self.logger = logging.getLogger(f"agents.{agent_name}")

    @abstractmethod
    async def process(self, context: AgentContext) -> AgentResult:
        pass

    async def validate_input(self, context: AgentContext) -> bool:
        return bool(context.input_data)

    async def enhance_with_rag(self, query: str, context: AgentContext, top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            return await self.rag_service.retrieve(
                query=query,
                institution_id=context.institution_id,
                top_k=top_k,
            )
        except Exception as e:
            self.logger.warning(f"RAG retrieval failed: {e}")
            return []

    async def call_llm(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[str] = None,
    ) -> str:
        return await self.llm_service.generate(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    async def update_shared_memory(self, key: str, value: Any, context: AgentContext):
        memory_key = f"{context.workflow_id}:{key}"
        await self.shared_memory.set(memory_key, value)
        context.shared_memory[key] = value
        context.updated_at = datetime.now()

    async def get_from_shared_memory(self, key: str, context: AgentContext) -> Any:
        if key in context.shared_memory:
            return context.shared_memory[key]
        memory_key = f"{context.workflow_id}:{key}"
        value = await self.shared_memory.get(memory_key)
        if value:
            context.shared_memory[key] = value
        return value

    def format_error_result(self, error_message: str, processing_time: float, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name=self.agent_name,
            success=False,
            data={},
            error=error_message,
            processing_time=processing_time,
            metadata={"agent_id": self.agent_id, "workflow_id": context.workflow_id},
        )