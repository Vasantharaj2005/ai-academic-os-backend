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
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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

router = APIRouter()
logger = logging.getLogger(__name__)


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
