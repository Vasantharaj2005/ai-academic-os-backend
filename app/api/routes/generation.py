"""Course generation API routes - triggers multi-agent AI pipeline."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import logging

from app.services.database.session import get_db
from app.models.database.user import User
from app.models.database.course import Course, CourseStatus
from app.models.schemas.generation import GenerationRequest, GenerationStatusResponse, GenerationResultResponse
from app.api.dependencies.auth_deps import get_current_active_user
from app.core.orchestrator import orchestrator
from app.utils.helpers import generate_workflow_id, now_iso

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/{course_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(
    course_id: str,
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start AI course generation pipeline.
    Returns workflow_id for status tracking.
    Generation runs asynchronously in background.
    """
    # Get course
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.creator_id == current_user.id)
    )
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    if course.status == CourseStatus.GENERATING and not request.force_regenerate:
        raise HTTPException(
            status_code=409,
            detail={"message": "Generation already in progress", "code": "GENERATION_IN_PROGRESS"},
        )

    # Generate workflow ID
    workflow_id = generate_workflow_id("wf")

    # Reset course status — clears any previous FAILED state / stale error
    course.status = CourseStatus.GENERATING
    course.workflow_id = workflow_id
    course.generation_progress = 0.0
    course.error_message = None
    course.completed_at = None
    await db.commit()

    # Build course data dict for agents
    course_data = {
        "id": course.id,
        "title": course.title,
        "code": course.code,
        "description": course.description,
        "program": course.program.value,
        "department": course.department,
        "semester": course.semester,
        "credits": course.credits,
        "institution_id": current_user.institution_id or "default",
        "additional_context": request.additional_context,
    }

    # Launch generation in background
    background_tasks.add_task(
        _run_generation_task,
        workflow_id=workflow_id,
        course_id=course_id,
        course_data=course_data,
        user_id=current_user.id,
        institution_id=current_user.institution_id or "default",
        mode=request.mode.value,
    )

    logger.info(f"Generation started: workflow={workflow_id}, course={course_id}")

    return {
        "workflow_id": workflow_id,
        "course_id": course_id,
        "status": "generating",
        "message": "Generation started. Use /status endpoint to track progress.",
        "started_at": now_iso(),
    }


@router.get("/{course_id}/status")
async def get_generation_status(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current generation status for a course."""
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.creator_id == current_user.id)
    )
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    workflow_status = None
    if course.workflow_id:
        workflow_status = await orchestrator.get_workflow_status(course.workflow_id)

    agents = []
    if workflow_status:
        for agent_name, agent_info in workflow_status.get("agents", {}).items():
            agents.append({
                "agent_name": agent_name,
                "status": agent_info.get("status", "pending"),
                "updated_at": agent_info.get("updated_at"),
            })

    return {
        "workflow_id": course.workflow_id,
        "course_id": course.id,
        "status": course.status.value,
        "progress": course.generation_progress,
        "agents": agents,
        "started_at": workflow_status.get("started_at") if workflow_status else None,
        # Only surface error_message when the course is actually in FAILED state
        # (prevents stale errors from old runs appearing during a new generation)
        "error": course.error_message if course.status == CourseStatus.FAILED else None,
    }


@router.get("/{course_id}/result", response_model=GenerationResultResponse)
async def get_generation_result(
    course_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full generation result for a completed course."""
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.creator_id == current_user.id)
    )
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    if course.status not in [CourseStatus.COMPLETED, CourseStatus.PUBLISHED]:
        raise HTTPException(
            status_code=400,
            detail={"message": f"Course generation not complete. Status: {course.status.value}", "code": "NOT_COMPLETE"},
        )

    return GenerationResultResponse(
        workflow_id=course.workflow_id or "",
        course_id=course.id,
        success=True,
        generated_components=["curriculum", "semester_plan", "assessments", "obe_report", "analytics"],
        curriculum=course.curriculum_data,
        semester_plan=course.semester_plan_data,
        assessments=course.assessment_data,
        obe_report=course.obe_data,
        analytics=course.analytics_data,
        validation_report=getattr(course, "validation_data", None),
        file_urls={
            "syllabus_pdf": course.syllabus_pdf_url,
            "presentations": course.presentation_urls or [],
        },
        duration_seconds=0,
    )


@router.post("/{course_id}/regenerate/{component}")
async def regenerate_component(
    course_id: str,
    component: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate a specific component of the course."""
    valid_components = ["curriculum", "semester", "assessments", "obe", "analytics", "validation"]
    if component not in valid_components:
        raise HTTPException(status_code=400, detail={"message": f"Invalid component. Valid: {valid_components}", "code": "INVALID_COMPONENT"})

    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.creator_id == current_user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail={"message": "Course not found", "code": "NOT_FOUND"})

    workflow_id = generate_workflow_id("wf-regen")
    mode_map = {
        "curriculum": "curriculum_only",
        "semester": "semester_only",
        "assessments": "assessments_only",
        "obe": "obe_only",
        "analytics": "full",
        "validation": "validation_only",
    }

    course_data = {
        "id": course.id, "title": course.title, "program": course.program.value,
        "department": course.department, "semester": course.semester, "credits": course.credits,
    }
    
    # If validating, we must pass existing data to seed the orchestrator
    existing_state = {}
    if component == "validation":
        existing_state = {
            "curriculum":    course.curriculum_data,
            "semester_plan": course.semester_plan_data,
            "assessments":   course.assessment_data,
            "obe_report":    course.obe_data,
            # Note: content is not currently persisted in Course model, so validator will skip content checks
        }

    background_tasks.add_task(
        _run_generation_task,
        workflow_id=workflow_id,
        course_id=course_id,
        course_data=course_data,
        user_id=current_user.id,
        institution_id=current_user.institution_id or "default",
        mode=mode_map.get(component, "full"),
        existing_state=existing_state,
    )

    return {"workflow_id": workflow_id, "component": component, "status": "regenerating"}


async def _run_generation_task(
    workflow_id: str,
    course_id: str,
    course_data: dict,
    user_id: str,
    institution_id: str,
    mode: str,
    existing_state: dict = None,
):
    """Background task that runs the full AI generation pipeline."""
    from app.services.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await orchestrator.run_full_generation(
                course_data=course_data,
                user_id=user_id,
                institution_id=institution_id,
                mode=mode,
                workflow_id=workflow_id,
                existing_state=existing_state,
            )

            # Save results to database
            db_result = await db.execute(select(Course).where(Course.id == course_id))
            course = db_result.scalar_one_or_none()

            if course:
                course.status = CourseStatus.COMPLETED
                course.curriculum_data = result.get("curriculum")
                course.semester_plan_data = result.get("semester_plan")
                course.assessment_data = result.get("assessments")
                course.obe_data = result.get("obe_report")
                course.analytics_data = result.get("analytics")
                
                # Only update validation data if it was generated
                if result.get("validation_report"):
                    course.validation_data = result.get("validation_report")
                    
                course.generation_progress = 100.0
                course.completed_at = datetime.utcnow()
                await db.commit()

            logger.info(f"Generation task completed: workflow={workflow_id}")

        except Exception as e:
            logger.error(f"Generation task failed: {e}", exc_info=True)
            try:
                db_result = await db.execute(select(Course).where(Course.id == course_id))
                course = db_result.scalar_one_or_none()
                if course:
                    course.status = CourseStatus.FAILED
                    course.error_message = str(e)
                    await db.commit()
            except Exception:
                pass