"""Course Pydantic schemas."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.database.course import CourseStatus, ProgramType


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    code: Optional[str] = None
    description: Optional[str] = None
    program: ProgramType
    department: str
    semester: int = Field(..., ge=1, le=8)
    credits: int = Field(4, ge=1, le=6)
    academic_year: Optional[str] = None
    tags: Optional[List[str]] = []
    is_public: bool = False


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    department: Optional[str] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class CourseResponse(BaseModel):
    id: str
    title: str
    code: Optional[str]
    description: Optional[str]
    program: str
    department: str
    semester: int
    credits: int
    academic_year: Optional[str]
    status: CourseStatus
    workflow_id: Optional[str]
    generation_progress: float
    error_message: Optional[str]
    syllabus_pdf_url: Optional[str]
    presentation_urls: Optional[List[str]]
    is_public: bool
    tags: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class CourseDetailResponse(CourseResponse):
    curriculum_data: Optional[Dict[str, Any]]
    semester_plan_data: Optional[Dict[str, Any]]
    assessment_data: Optional[Dict[str, Any]]
    obe_data: Optional[Dict[str, Any]]
    analytics_data: Optional[Dict[str, Any]]


class CourseListResponse(BaseModel):
    items: List[CourseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int