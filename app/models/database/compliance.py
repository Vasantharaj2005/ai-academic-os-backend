"""Compliance (OBE) database model."""
from sqlalchemy import Column, String, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.services.database.session import Base
from app.utils.helpers import generate_uuid


class Compliance(Base):
    __tablename__ = "compliance_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=False, index=True)

    report_type = Column(String(100), nullable=False, default="OBE")
    obe_framework = Column(String(100), nullable=True)  # NBA, NAAC, etc.

    # CO-PO Mapping matrix
    co_po_mapping = Column(JSON, nullable=True)
    co_pso_mapping = Column(JSON, nullable=True)

    # Attainment targets
    co_attainment_targets = Column(JSON, nullable=True)
    po_attainment_targets = Column(JSON, nullable=True)

    # Bloom's analysis
    blooms_distribution = Column(JSON, nullable=True)

    compliance_score = Column(Float, nullable=True)
    recommendations = Column(JSON, nullable=True)

    pdf_url = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())