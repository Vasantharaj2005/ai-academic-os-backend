"""Generation request/response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from enum import Enum


class GenerationMode(str, Enum):
    FULL = "full"            # All agents
    CURRICULUM_ONLY = "curriculum_only"
    SEMESTER_ONLY = "semester_only"
    ASSESSMENTS_ONLY = "assessments_only"
    OBE_ONLY = "obe_only"


class GenerationRequest(BaseModel):
    course_id: str
    mode: GenerationMode = GenerationMode.FULL
    # SEC-009: Limit and sanitize user-supplied context to mitigate prompt injection
    additional_context: Optional[str] = Field(None, max_length=2000)
    reference_docs: Optional[List[str]] = []  # S3 keys
    force_regenerate: bool = False

    @field_validator("additional_context")
    @classmethod
    def sanitize_context(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace and enforce length cap to reduce prompt injection risk."""
        if v is None:
            return v
        sanitized = v.strip()
        # Remove null bytes and other control chars that could manipulate prompts
        sanitized = "".join(c for c in sanitized if ord(c) >= 32 or c in "\n\t")
        return sanitized[:2000] if sanitized else None


class AgentStatus(BaseModel):
    agent_name: str
    status: str  # pending | running | completed | failed
    progress: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_summary: Optional[str] = None


class GenerationStatusResponse(BaseModel):
    workflow_id: str
    course_id: str
    status: str  # running | completed | failed
    overall_progress: float
    agents: List[AgentStatus]
    started_at: str
    estimated_completion: Optional[str] = None
    error: Optional[str] = None


class GenerationResultResponse(BaseModel):
    workflow_id: str
    course_id: str
    success: bool
    generated_components: List[str]
    curriculum: Optional[Dict[str, Any]] = None
    semester_plan: Optional[Dict[str, Any]] = None
    # assessments is a dict from AssessmentAgent, e.g. {"assessments": [...], "question_bank": {...}}
    assessments: Optional[Dict[str, Any]] = None
    obe_report: Optional[Dict[str, Any]] = None
    analytics: Optional[Dict[str, Any]] = None
    file_urls: Dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    errors: List[str] = Field(default_factory=list)


# ── Standard API Responses ──────────────────────────────────────────
class APIResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    code: str
    details: Optional[Any] = None