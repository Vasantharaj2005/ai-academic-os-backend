"""Assessment routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.database.course import Course
from app.api.dependencies.auth_deps import get_current_active_user

router = APIRouter()


@router.get("/{course_id}/assessments")
async def get_assessments(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all assessments for a course."""
    result = await db.execute(select(Course).where(Course.id == course_id, Course.creator_id == current_user.id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    return {
        "course_id": course_id,
        "assessments": course.assessment_data or {},
    }


@router.get("/{course_id}/question-bank")
async def get_question_bank(
    course_id: str,
    bloom_level: str = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get question bank for a course, optionally filtered by Bloom's level."""
    result = await db.execute(select(Course).where(Course.id == course_id, Course.creator_id == current_user.id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    assessment_data = course.assessment_data or {}
    qb = assessment_data.get("question_bank", {})

    if bloom_level:
        by_level = qb.get("by_bloom_level", {})
        return {"bloom_level": bloom_level, "questions": by_level.get(bloom_level, [])}

    return {"course_id": course_id, "question_bank": qb}