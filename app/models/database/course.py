"""Course database model."""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Enum as SAEnum, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.services.database.session import Base
from app.utils.helpers import generate_uuid


class CourseStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    PUBLISHED = "published"


class ProgramType(str, enum.Enum):
    BTECH = "B.Tech"
    MTECH = "M.Tech"
    MBA = "MBA"
    MCA = "MCA"
    BCA = "BCA"
    BSC = "B.Sc"
    MSC = "M.Sc"
    PHD = "Ph.D"


class Course(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    creator_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    institution_id = Column(String(36), nullable=True, index=True)

    # Course Info
    title = Column(String(500), nullable=False)
    code = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    program = Column(SAEnum(ProgramType), nullable=False)
    department = Column(String(200), nullable=False)
    semester = Column(Integer, nullable=False)
    credits = Column(Integer, nullable=False, default=4)
    academic_year = Column(String(20), nullable=True)

    # Status
    status = Column(SAEnum(CourseStatus), default=CourseStatus.DRAFT, nullable=False)
    workflow_id = Column(String(50), nullable=True, index=True)
    generation_progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)

    # Generated Content (stored as JSON for flexibility)
    curriculum_data = Column(JSON, nullable=True)
    semester_plan_data = Column(JSON, nullable=True)
    assessment_data = Column(JSON, nullable=True)
    obe_data = Column(JSON, nullable=True)
    analytics_data = Column(JSON, nullable=True)

    # File URLs
    syllabus_pdf_url = Column(Text, nullable=True)
    presentation_urls = Column(JSON, nullable=True)  # list of URLs

    # Settings
    is_public = Column(Boolean, default=False)
    tags = Column(JSON, nullable=True)  # list of strings

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    creator = relationship("User", back_populates="courses")
    syllabi = relationship("Syllabus", back_populates="course", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="course", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Course {self.title} ({self.status})>"