"""Agent management routes."""

from fastapi import APIRouter, Depends
from app.models.database.user import User
from app.api.dependencies.auth_deps import get_current_active_user

router = APIRouter()


@router.get("/")
async def list_agents(current_user: User = Depends(get_current_active_user)):
    """List all available agents and their status."""
    return {
        "agents": [
            {"name": "CurriculumAgent", "id": "curr-001", "description": "Generates course syllabus and CLOs"},
            {"name": "SemesterAgent", "id": "sem-001", "description": "Creates 16-week teaching plan"},
            {"name": "ContentAgent", "id": "cnt-001", "description": "Generates lecture content and slide decks"},
            {"name": "AssessmentAgent", "id": "ass-001", "description": "Creates assessments and question bank"},
            {"name": "OBEAgent", "id": "obe-001", "description": "CO-PO mapping and NBA/NAAC compliance"},
            {"name": "AnalyticsAgent", "id": "anl-001", "description": "Learning analytics and performance prediction"},
        ]
    }