"""Course management API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import math
import logging

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.database.course import Course, CourseStatus
from app.models.schemas.course import CourseCreate, CourseUpdate, CourseResponse, CourseDetailResponse, CourseListResponse
from app.api.dependencies.auth_deps import get_current_active_user
from app.utils.helpers import generate_uuid

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    course_in: CourseCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new course."""
    course = Course(
        id=generate_uuid(),
        creator_id=current_user.id,
        institution_id=current_user.institution_id,
        title=course_in.title,
        code=course_in.code,
        description=course_in.description,
        program=course_in.program,
        department=course_in.department,
        semester=course_in.semester,
        credits=course_in.credits,
        academic_year=course_in.academic_year,
        is_public=course_in.is_public,
        tags=course_in.tags,
        status=CourseStatus.DRAFT,
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


@router.get("/", response_model=CourseListResponse)
async def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[CourseStatus] = None,
    program: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's courses with filtering and pagination."""
    query = select(Course).where(Course.creator_id == current_user.id)

    if status:
        query = query.where(Course.status == status)
    if program:
        query = query.where(Course.program == program)
    if search:
        query = query.where(Course.title.ilike(f"%{search}%"))

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Paginate
    query = query.order_by(Course.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    courses = result.scalars().all()

    return CourseListResponse(
        items=courses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size),
    )


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get course details by ID."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    # Check access
    if course.creator_id != current_user.id and not course.is_public:
        raise HTTPException(status_code=403, detail={"message": "Access denied", "code": "FORBIDDEN"})

    return course


@router.patch("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: str,
    update: CourseUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update course metadata."""
    result = await db.execute(select(Course).where(Course.id == course_id, Course.creator_id == current_user.id))
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(course, field, value)

    await db.commit()
    await db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a course."""
    result = await db.execute(select(Course).where(Course.id == course_id, Course.creator_id == current_user.id))
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    await db.delete(course)
    await db.commit()