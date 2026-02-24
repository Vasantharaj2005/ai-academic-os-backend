"""Report generation Celery tasks."""

import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="report_tasks.generate_pdf_report")
def generate_pdf_report(course_id: str, report_type: str):
    """Generate PDF report for a course."""
    logger.info(f"Generating {report_type} PDF for course {course_id}")
    # PDF generation logic would go here using reportlab/weasyprint
    return {"status": "completed", "course_id": course_id, "report_type": report_type}