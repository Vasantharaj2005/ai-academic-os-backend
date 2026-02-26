"""
Question Paper Generation API
POST /api/v1/question-papers/generate  → generate + export in one call
GET  /api/v1/question-papers/exam-types → list supported exam types with defaults
"""

import os
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.database.course import Course, CourseStatus
from app.api.dependencies.auth_deps import get_current_active_user
from app.models.schemas.question_paper import (
    QuestionPaperRequest, QuestionPaperResponse,
    EXAM_DEFAULTS, ExamType, ExportFormat,
)
from app.services.storage.question_paper_renderer import (
    render_question_paper_pdf,
    render_question_paper_html,
)
from app.agents.question_paper_agent import QuestionPaperAgent
from app.agents.base_agent import AgentContext
from app.services.ai.llm_service import llm_service

router = APIRouter()
logger = logging.getLogger(__name__)

_paper_agent = QuestionPaperAgent(llm_service=llm_service)


def _cleanup(path: str):
    try:
        os.unlink(path)
    except Exception:
        pass


# ── List exam types ────────────────────────────────────────────────────────────

@router.get(
    "/exam-types",
    summary="List supported exam types and their defaults",
    tags=["📝 Question Papers"],
)
async def list_exam_types():
    """
    Returns all supported exam types with their default duration, marks,
    parts, and instructions. Useful for pre-filling the UI.
    """
    result = {}
    for exam_type in ExamType:
        defaults = EXAM_DEFAULTS.get(exam_type.value, {})
        result[exam_type.value] = {
            "duration_minutes": defaults.get("duration_minutes"),
            "total_marks":      defaults.get("total_marks"),
            "modules_covered":  defaults.get("modules_covered"),
            "instructions":     defaults.get("instructions"),
            "parts": [
                {
                    "label":         p["label"],
                    "type":          p["type"],
                    "num_questions": p["num_questions"],
                    "marks_each":    p["marks_each"],
                    **({"choose": p["choose"]} if "choose" in p else {}),
                    **({"either_or": p["either_or"]} if "either_or" in p else {}),
                }
                for p in defaults.get("parts", [])
            ],
        }
    return {"exam_types": result}


# ── Generate + export ──────────────────────────────────────────────────────────

@router.post(
    "/generate",
    summary="Generate a question paper and download as PDF or HTML",
    tags=["📝 Question Papers"],
)
async def generate_question_paper(
    request: QuestionPaperRequest,
    background_tasks: BackgroundTasks,
    include_answer_hints: bool = Query(
        False,
        description="Include answer key hints in the exported file (useful for faculty copy)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a complete, AI-crafted question paper for the given `exam_type`
    and return it as a downloadable PDF or HTML file.

    **Exam types:** CIA-1, CIA-2, Model Exam, End Semester, Lab Record, Quiz, Viva, Assignment

    The agent reads the course's CLOs and module topics to generate
    syllabus-aligned questions at the correct Bloom's taxonomy level.
    Duration, marks, and part structure are pre-configured per exam type
    but can be overridden in the request body.
    """

    # 1. Fetch the course
    result = await db.execute(
        select(Course).where(Course.id == request.course_id, Course.creator_id == current_user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    # Warn but don't block — paper can still be generated with empty curriculum
    if course.status not in (CourseStatus.COMPLETED, CourseStatus.PUBLISHED):
        logger.warning(
            f"Course {course.id} is not COMPLETED (status={course.status.value}). "
            "Question paper will be generated with available curriculum data."
        )

    # 2. Resolve defaults for exam type
    exam_type = request.exam_type.value
    defaults  = EXAM_DEFAULTS.get(exam_type, EXAM_DEFAULTS["CIA-1"])

    duration_minutes = request.duration_minutes or defaults["duration_minutes"]
    total_marks      = request.total_marks      or defaults["total_marks"]
    instructions     = request.instructions     or defaults["instructions"]
    modules_covered  = request.modules_covered  or defaults.get("modules_covered", "All Modules")
    institution_name = request.institution_name or "My Institution"
    department       = request.department       or course.department
    subject_code     = request.subject_code     or course.code
    academic_year    = request.academic_year    or course.academic_year or datetime.now().strftime("%Y-%m")

    # 3. Run the AI agent
    paper_id = uuid.uuid4().hex[:10]
    context = AgentContext(
        workflow_id=f"qpaper-{paper_id}",
        course_id=course.id,
        user_id=current_user.id,
        institution_id=current_user.institution_id or "default",
        input_data={
            "exam_type":   exam_type,
            "course_data": {
                "title":             course.title,
                "curriculum_data":   course.curriculum_data or {},
                "assessment_data":   course.assessment_data or {},
            },
            "request": {
                "modules_covered":    modules_covered,
                "difficulty":         request.difficulty.value,
                "additional_context": request.additional_context or "",
            },
        },
    )

    agent_result = await _paper_agent.process(context)
    if not agent_result.success:
        logger.error(f"Question paper AI generation failed for {request.course_id}: {agent_result.error}")
        raise HTTPException(
            status_code=500,
            detail={"message": "AI generation failed. Please try again.", "code": "AGENT_ERROR"},
        )

    # 4. Merge metadata + generated sections
    paper_data = {
        "paper_id":         paper_id,
        "course_id":        course.id,
        "course_title":     course.title,
        "exam_type":        exam_type,
        "institution_name": institution_name,
        "department":       department,
        "subject_code":     subject_code,
        "academic_year":    academic_year,
        "duration_minutes": duration_minutes,
        "total_marks":      total_marks,
        "modules_covered":  modules_covered,
        "instructions":     instructions,
        "generated_at":     datetime.now().isoformat(),
        **agent_result.data,   # sections, part_count, total_generated
    }

    # 5. Render to requested format
    export_fmt = request.export_format

    if export_fmt == ExportFormat.PDF:
        file_path = await render_question_paper_pdf(
            paper_data, include_answer_hints=include_answer_hints
        )
        media_type = "application/pdf"
        suffix     = "pdf"
    else:
        file_path = await render_question_paper_html(
            paper_data, include_answer_hints=include_answer_hints
        )
        media_type = "text/html"
        suffix     = "html"

    safe_type = exam_type.lower().replace(" ", "_").replace("-", "")
    safe_code = (subject_code or course.id).replace(" ", "")
    filename  = f"{safe_type}_{safe_code}.{suffix}"

    background_tasks.add_task(_cleanup, file_path)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )
