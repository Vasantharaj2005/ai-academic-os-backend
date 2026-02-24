"""Assessment database model."""
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.services.database.session import Base
from app.utils.helpers import generate_uuid


class AssessmentType(str, enum.Enum):
    QUIZ = "quiz"
    MIDTERM = "midterm"
    FINAL = "final"
    ASSIGNMENT = "assignment"
    LAB = "lab"
    PROJECT = "project"
    VIVA = "viva"


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False, index=True)

    title = Column(String(500), nullable=False)
    assessment_type = Column(SAEnum(AssessmentType), nullable=False)
    total_marks = Column(Integer, default=100)
    duration_minutes = Column(Integer, nullable=True)
    weightage = Column(Float, nullable=True)  # percentage
    week_number = Column(Integer, nullable=True)

    # Questions organized by Bloom's taxonomy
    questions = Column(JSON, nullable=True)   # list of question objects
    bloom_distribution = Column(JSON, nullable=True)  # {level: count}
    clo_mapping = Column(JSON, nullable=True)  # {clo_id: [question_ids]}

    instructions = Column(Text, nullable=True)
    pdf_url = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    course = relationship("Course", back_populates="assessments")