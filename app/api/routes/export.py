"""
PDF Export API Routes
Endpoints to download AI-generated course content as PDF files.

Routes:
  GET  /{course_id}/export/syllabus           → Syllabus PDF
  GET  /{course_id}/export/question-paper/{n} → Single question paper PDF
  GET  /{course_id}/export/obe-report         → OBE compliance report PDF
  POST /{course_id}/export/bundle             → All PDFs as ZIP
"""

import os
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.database.course import Course, CourseStatus
from app.api.dependencies.auth_deps import get_current_active_user
from app.services.storage.pdf_generator import (
    generate_syllabus_pdf,
    generate_question_paper_pdf,
    generate_obe_report_pdf,
    generate_course_bundle,
)
from app.models.schemas.question_paper import (
    QuestionPaperRequest, EXAM_DEFAULTS, ExportFormat
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

# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_completed_course(course_id: str, user: User, db: AsyncSession) -> Course:
    """Fetch a course that belongs to the user and has completed generation."""
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.creator_id == user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})
    if course.status not in (CourseStatus.COMPLETED, CourseStatus.PUBLISHED):
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Course generation not complete (status: {course.status.value}). "
                            "Run /generate first.",
                "code": "NOT_COMPLETE",
            },
        )
    return course


def _cleanup(path: str):
    """Background task to delete a temporary file."""
    try:
        os.unlink(path)
    except Exception:
        pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{course_id}/export/syllabus", summary="Download Syllabus PDF")
async def export_syllabus(
    course_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and download the full course syllabus as a PDF.
    Includes: course objectives, CLOs, module-wise topics, weekly plan,
    assessment schedule, and textbooks.
    """
    course = await _get_completed_course(course_id, current_user, db)
    try:
        pdf_path = await generate_syllabus_pdf(course)
    except Exception as e:
        logger.error(f"Syllabus PDF failed for {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"message": "Syllabus PDF generation failed. Please try again.", "code": "PDF_ERROR"})

    background_tasks.add_task(_cleanup, pdf_path)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"syllabus_{course.code or course_id}.pdf",
    )


@router.get("/{course_id}/export/question-paper/{assessment_index}",
            summary="Download Question Paper PDF")
async def export_question_paper(
    course_id: str,
    assessment_index: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and download a single question paper PDF.
    `assessment_index` is 0-based (0 = first assessment, 1 = second, …).
    """
    course = await _get_completed_course(course_id, current_user, db)

    assessment_data = course.assessment_data or {}
    assessments = assessment_data.get("assessments", [])

    if not assessments:
        raise HTTPException(status_code=404, detail={"message": "No assessments found for this course", "code": "NOT_FOUND"})
    if assessment_index >= len(assessments):
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Assessment index {assessment_index} out of range. "
                            f"This course has {len(assessments)} assessment(s) (0-indexed).",
                "code": "NOT_FOUND",
            },
        )

    asmt = assessments[assessment_index]
    try:
        pdf_path = await generate_question_paper_pdf(asmt, course_title=course.title)
    except Exception as e:
        logger.error(f"Question paper PDF failed for {course_id}[{assessment_index}]: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"message": "Question paper PDF generation failed. Please try again.", "code": "PDF_ERROR"})

    asmt_type = asmt.get("type", "assessment").lower().replace(" ", "_")
    background_tasks.add_task(_cleanup, pdf_path)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"qpaper_{asmt_type}_{course.code or course_id}.pdf",
    )


@router.get("/{course_id}/export/obe-report", summary="Download OBE Report PDF")
async def export_obe_report(
    course_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and download the OBE / CO-PO compliance report PDF.
    Includes: CO-PO mapping matrix, gap analysis, recommendations, NBA notes.
    """
    course = await _get_completed_course(course_id, current_user, db)
    try:
        pdf_path = await generate_obe_report_pdf(course.obe_data or {}, course_title=course.title)
    except Exception as e:
        logger.error(f"OBE report PDF failed for {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"message": "OBE report PDF generation failed. Please try again.", "code": "PDF_ERROR"})

    background_tasks.add_task(_cleanup, pdf_path)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"obe_report_{course.code or course_id}.pdf",
    )


@router.post("/{course_id}/export/bundle", summary="Download All Materials as ZIP")
async def export_bundle(
    course_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate all PDFs (syllabus + all question papers + OBE report)
    and return them as a single ZIP archive.
    """
    course = await _get_completed_course(course_id, current_user, db)
    try:
        zip_path = await generate_course_bundle(course)
    except Exception as e:
        logger.error(f"Bundle generation failed for {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"message": "Bundle generation failed. Please try again.", "code": "PDF_ERROR"})

    background_tasks.add_task(_cleanup, zip_path)
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"course_bundle_{course.code or course_id}.zip",
    )


@router.post("/{course_id}/export/generate-question-paper", summary="Generate & Download Custom Question Paper")
async def generate_custom_question_paper(
    course_id: str,
    request: QuestionPaperRequest,
    background_tasks: BackgroundTasks,
    include_answer_hints: bool = Query(False, description="Include answer key hints in the exported file"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a complete, AI-crafted question paper for the given exam_type 
    and return it as a downloadable PDF or HTML file.
    """
    # Override body course_id with path course_id to ensure consistency
    request.course_id = course_id

    # 1. Fetch the course
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.creator_id == current_user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

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
        logger.error(f"Question paper AI generation failed for {course_id}: {agent_result.error}")
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
        **agent_result.data,
    }

    # 5. Render to requested format
    export_fmt = request.export_format
    if export_fmt == ExportFormat.PDF:
        file_path = await render_question_paper_pdf(
            paper_data, include_answer_hints=include_answer_hints
        )
        media_type = "application/pdf"
        suffix = "pdf"
    else:
        file_path = await render_question_paper_html(
            paper_data, include_answer_hints=include_answer_hints
        )
        media_type = "text/html"
        suffix = "html"

    safe_type = exam_type.lower().replace(" ", "_").replace("-", "")
    safe_code = (subject_code or course.id).replace(" ", "")
    filename  = f"{safe_type}_{safe_code}.{suffix}"

    background_tasks.add_task(_cleanup, file_path)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )
