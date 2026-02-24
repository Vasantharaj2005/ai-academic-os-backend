"""Syllabus database model."""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.services.database.session import Base
from app.utils.helpers import generate_uuid


class Syllabus(Base):
    __tablename__ = "syllabi"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False, index=True)

    version = Column(Integer, default=1)
    objectives = Column(JSON, nullable=True)       # list of strings
    learning_outcomes = Column(JSON, nullable=True) # list of CLO dicts
    modules = Column(JSON, nullable=True)           # list of module dicts
    textbooks = Column(JSON, nullable=True)
    references = Column(JSON, nullable=True)
    prerequisites = Column(JSON, nullable=True)
    assessment_weightage = Column(JSON, nullable=True)
    week_plan = Column(JSON, nullable=True)         # 16-week plan

    is_current = Column(Boolean, default=True)
    pdf_url = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    course = relationship("Course", back_populates="syllabi")