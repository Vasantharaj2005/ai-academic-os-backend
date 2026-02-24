"""Analytics routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.database.course import Course
from app.api.dependencies.auth_deps import get_current_active_user

router = APIRouter()


@router.get("/{course_id}")
async def get_analytics(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics and predictions for a course."""
    result = await db.execute(select(Course).where(Course.id == course_id, Course.creator_id == current_user.id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    return {"course_id": course_id, "analytics": course.analytics_data or {}}