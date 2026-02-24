"""
Academic PDF Generator Service
Handles: Syllabus, Question Papers, OBE Reports, Full Bundle (ZIP)
Uses ReportLab for professional formatting following AICTE/NBA standards.
"""

import os
import uuid
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak, HRFlowable,
)

logger = logging.getLogger(__name__)

# ── Output directory ───────────────────────────────────────────────────────────
PDF_OUTPUT_DIR = Path("generated_pdfs")
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Brand colours ──────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1e3a8a")
STEEL  = colors.HexColor("#334155")
SLATE  = colors.HexColor("#475569")
LIGHT  = colors.HexColor("#f8fafc")
BORDER = colors.HexColor("#cbd5e1")


# ── Shared style builder ───────────────────────────────────────────────────────

def _build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle("DocTitle",   parent=styles["Heading1"],
        fontSize=20, alignment=TA_CENTER, spaceAfter=6,
        textColor=NAVY, fontName="Helvetica-Bold"))

    styles.add(ParagraphStyle("DocSubtitle", parent=styles["Heading2"],
        fontSize=13, alignment=TA_CENTER, spaceAfter=14,
        textColor=STEEL, fontName="Helvetica"))

    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading3"],
        fontSize=12, spaceBefore=14, spaceAfter=6,
        textColor=NAVY, fontName="Helvetica-Bold",
        borderPad=4, leftIndent=0))

    styles.add(ParagraphStyle("Body10",     parent=styles["Normal"],
        fontSize=10, spaceAfter=4, leading=14))

    styles.add(ParagraphStyle("Bullet10",   parent=styles["Normal"],
        fontSize=10, leftIndent=16, spaceAfter=3,
        bulletIndent=6))

    styles.add(ParagraphStyle("Caption",    parent=styles["Normal"],
        fontSize=8, textColor=SLATE, spaceAfter=2))

    return styles


def _header_table_style():
    return TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",         (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND",   (0, 1), (-1, -1), LIGHT),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
    ])


def _meta_block(story, styles, pairs: List[tuple]):
    """Render a 2-column metadata table (label: value pairs)."""
    data = [[f"{k}:  {v}" for k, v in pairs[i:i+2]] for i in range(0, len(pairs), 2)]
    t = Table(data, colWidths=[3.2 * inch, 3.2 * inch])
    t.setStyle(TableStyle([
        ("FONTNAME",     (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(t)


# ── Syllabus PDF ───────────────────────────────────────────────────────────────

async def generate_syllabus_pdf(
    course: Any,                   # SQLAlchemy Course ORM object
    output_filename: Optional[str] = None,
) -> str:
    """
    Generate a professional A4 syllabus PDF from a completed Course.
    Returns the absolute file path of the generated PDF.
    """
    styles = _build_styles()
    curriculum    = course.curriculum_data    or {}
    semester_plan = course.semester_plan_data or {}

    filename  = output_filename or f"syllabus_{course.id}_{_ts()}.pdf"
    filepath  = str(PDF_OUTPUT_DIR / filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        rightMargin=64, leftMargin=64, topMargin=64, bottomMargin=64,
        title=f"{course.title} – Syllabus",
        author="AI Academic OS",
    )
    story: List = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story.append(Paragraph("AI ACADEMIC OPERATING SYSTEM", styles["DocTitle"]))
    story.append(Paragraph(course.title.upper(), styles["DocSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=10))

    _meta_block(story, styles, [
        ("Program",  course.program.value if hasattr(course.program, "value") else str(course.program)),
        ("Semester", str(course.semester)),
        ("Credits",  str(course.credits)),
        ("Dept",     course.department),
        ("Status",   course.status.value if hasattr(course.status, "value") else str(course.status)),
        ("Generated",datetime.now().strftime("%d %b %Y")),
    ])
    story.append(Spacer(1, 0.25 * inch))

    # ── Course Objectives ──────────────────────────────────────────────────────
    story.append(Paragraph("COURSE OBJECTIVES", styles["SectionHead"]))
    for i, obj in enumerate(curriculum.get("course_objectives", []), 1):
        story.append(Paragraph(f"{i}.  {obj}", styles["Bullet10"]))
    story.append(Spacer(1, 0.15 * inch))

    # ── CLO Table ─────────────────────────────────────────────────────────────
    story.append(Paragraph("COURSE LEARNING OUTCOMES (CLOs)", styles["SectionHead"]))
    clos = curriculum.get("course_learning_outcomes", [])
    if clos:
        clo_data = [["CLO ID", "Statement", "Bloom's Level", "PO Mapping"]]
        for c in clos:
            stmt = c.get("statement", "")
            clo_data.append([
                c.get("id", ""),
                stmt[:70] + "…" if len(stmt) > 70 else stmt,
                c.get("bloom_level", "").capitalize(),
                ", ".join(c.get("po_mapping", [])),
            ])
        t = Table(clo_data, colWidths=[0.8*inch, 3.4*inch, 1.1*inch, 1.1*inch])
        t.setStyle(_header_table_style())
        story.append(t)
    story.append(Spacer(1, 0.15 * inch))

    # ── Modules ────────────────────────────────────────────────────────────────
    story.append(Paragraph("MODULE-WISE SYLLABUS", styles["SectionHead"]))
    for mod in curriculum.get("modules", []):
        title_txt = (
            f"<b>Module {mod.get('module_number','')}:  {mod.get('title','')}</b>"
            f"  <font color='#475569' size='9'>[{mod.get('hours',0)} hours]</font>"
        )
        story.append(Paragraph(title_txt, styles["Body10"]))
        for topic in mod.get("topics", []):
            story.append(Paragraph(f"•  {topic}", styles["Bullet10"]))
        clo_map = ", ".join(mod.get("clo_mapping", []))
        if clo_map:
            story.append(Paragraph(f"<i>CLOs: {clo_map}</i>", styles["Caption"]))
        story.append(Spacer(1, 0.08 * inch))

    # ── Textbooks ──────────────────────────────────────────────────────────────
    books = curriculum.get("textbooks", [])
    if books:
        story.append(Paragraph("TEXTBOOKS", styles["SectionHead"]))
        for i, b in enumerate(books, 1):
            story.append(Paragraph(
                f"{i}.  <b>{b.get('title','')}</b> — {b.get('author','')}, "
                f"{b.get('publisher','')}, {b.get('edition','')}, {b.get('year','')}",
                styles["Body10"],
            ))

    story.append(PageBreak())

    # ── Weekly Plan ───────────────────────────────────────────────────────────
    weeks = semester_plan.get("weeks", [])
    if weeks:
        story.append(Paragraph("WEEKLY TEACHING PLAN", styles["SectionHead"]))
        week_data = [["Week", "Module", "Topics", "Assessment"]]
        for w in weeks:
            topics_str = ", ".join(w.get("topics", [])[:2])
            if len(w.get("topics", [])) > 2:
                topics_str += " …"
            asmt = w.get("assessment") or {}
            week_data.append([
                str(w.get("week", "")),
                str(w.get("module", ""))[:18],
                topics_str[:50],
                asmt.get("type", "—") if isinstance(asmt, dict) else "—",
            ])
        t = Table(week_data, colWidths=[0.6*inch, 1.6*inch, 3.5*inch, 1.1*inch])
        t.setStyle(_header_table_style())
        story.append(t)
        story.append(Spacer(1, 0.15 * inch))

    # ── Assessment Schedule ───────────────────────────────────────────────────
    asmt_sched = semester_plan.get("assessment_schedule", [])
    if asmt_sched:
        story.append(Paragraph("ASSESSMENT SCHEDULE", styles["SectionHead"]))
        as_data = [["Week", "Type", "Topics Covered"]]
        for a in asmt_sched:
            topics_str = ", ".join(a.get("topics_covered", [])[:3])
            as_data.append([str(a.get("week", "")), a.get("type", ""), topics_str])
        t = Table(as_data, colWidths=[0.6*inch, 1.8*inch, 4.4*inch])
        t.setStyle(_header_table_style())
        story.append(t)

    doc.build(story)
    logger.info(f"Syllabus PDF generated: {filepath}")
    return filepath


# ── Question Paper PDF ────────────────────────────────────────────────────────

async def generate_question_paper_pdf(
    assessment_obj: Dict[str, Any],   # single assessment dict from assessment_data['assessments'][n]
    course_title: str = "Course",
    output_filename: Optional[str] = None,
) -> str:
    """
    Generate a formatted question-paper PDF for a single assessment dict.
    Returns the absolute file path.
    """
    styles = _build_styles()
    filename = output_filename or f"qpaper_{_ts()}.pdf"
    filepath = str(PDF_OUTPUT_DIR / filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        rightMargin=64, leftMargin=64, topMargin=64, bottomMargin=64,
        title=assessment_obj.get("assessment_title", "Question Paper"),
        author="AI Academic OS",
    )
    story: List = []

    story.append(Paragraph("AI ACADEMIC OPERATING SYSTEM", styles["DocTitle"]))
    story.append(Paragraph(course_title, styles["DocSubtitle"]))
    story.append(Paragraph(assessment_obj.get("assessment_title", "Question Paper"), styles["DocSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=8))

    _meta_block(story, styles, [
        ("Total Marks", str(assessment_obj.get("total_marks", "—"))),
        ("Duration",    f"{assessment_obj.get('duration_minutes', '—')} minutes"),
        ("Date",        datetime.now().strftime("%d %b %Y")),
        ("Reg. No.",    "___________________"),
    ])
    story.append(Spacer(1, 0.1 * inch))

    instr = assessment_obj.get("instructions", "Answer all questions.")
    story.append(Paragraph(f"<b>Instructions:</b>  {instr}", styles["Body10"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=10))

    # ── Sections ───────────────────────────────────────────────────────────────
    for section in assessment_obj.get("sections", []):
        sec_label  = section.get("section", "A")
        sec_type   = section.get("type", "")
        marks_each = section.get("marks_per_question", 0)
        story.append(Paragraph(
            f"Section {sec_label} —  {sec_type}  ({marks_each} marks each)",
            styles["SectionHead"],
        ))
        for qi, q in enumerate(section.get("questions", []), 1):
            story.append(Paragraph(f"{qi}.  {q.get('question', '')}", styles["Body10"]))
            for opt in q.get("options", []):
                story.append(Paragraph(f"     {opt}", styles["Bullet10"]))
            story.append(Paragraph(
                f"[Bloom's: {q.get('bloom_level','—').capitalize()} | {marks_each} marks]",
                styles["Caption"],
            ))
            story.append(Spacer(1, 0.06 * inch))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph("*** End of Question Paper ***",
        ParagraphStyle("EndMark", parent=styles["Normal"],
            alignment=TA_CENTER, textColor=SLATE, fontSize=9)))

    doc.build(story)
    logger.info(f"Question paper PDF generated: {filepath}")
    return filepath


# ── OBE Report PDF ────────────────────────────────────────────────────────────

async def generate_obe_report_pdf(
    obe_data: Dict[str, Any],
    course_title: str = "Course",
    output_filename: Optional[str] = None,
) -> str:
    """Generate an OBE / CO-PO compliance report PDF."""
    styles   = _build_styles()
    filename = output_filename or f"obe_report_{_ts()}.pdf"
    filepath = str(PDF_OUTPUT_DIR / filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            rightMargin=64, leftMargin=64,
                            topMargin=64, bottomMargin=64)
    story: List = []

    story.append(Paragraph("OUTCOME-BASED EDUCATION COMPLIANCE REPORT", styles["DocTitle"]))
    story.append(Paragraph(course_title, styles["DocSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=10))

    score = obe_data.get("compliance_score", 0)
    story.append(Paragraph(f"<b>Overall Compliance Score:  {score}%</b>", styles["Body10"]))
    story.append(Spacer(1, 0.15 * inch))

    # ── CO-PO Mapping ─────────────────────────────────────────────────────────
    mapping = obe_data.get("co_po_mapping", {})
    if mapping:
        story.append(Paragraph("CO-PO MAPPING MATRIX", styles["SectionHead"]))
        all_pos = sorted({po for m in mapping.values() for po in m.keys()})
        header  = ["CLO"] + all_pos
        rows    = [header]
        for clo_id, po_map in mapping.items():
            rows.append([clo_id] + [str(po_map.get(po, "—")) for po in all_pos])
        col_widths = [1.1 * inch] + [0.7 * inch] * len(all_pos)
        t = Table(rows, colWidths=col_widths)
        t.setStyle(_header_table_style())
        story.append(t)
        story.append(Spacer(1, 0.15 * inch))

    # ── Gap Analysis ──────────────────────────────────────────────────────────
    gaps = obe_data.get("gap_analysis", [])
    if gaps:
        story.append(Paragraph("GAP ANALYSIS", styles["SectionHead"]))
        for g in gaps:
            story.append(Paragraph(f"•  {g}", styles["Bullet10"]))
        story.append(Spacer(1, 0.1 * inch))

    # ── Recommendations ───────────────────────────────────────────────────────
    recs = obe_data.get("recommendations", [])
    if recs:
        story.append(Paragraph("RECOMMENDATIONS", styles["SectionHead"]))
        for i, r in enumerate(recs, 1):
            story.append(Paragraph(f"{i}.  {r}", styles["Bullet10"]))
        story.append(Spacer(1, 0.1 * inch))

    # ── NBA Notes ─────────────────────────────────────────────────────────────
    nba = obe_data.get("nba_compliance_notes", "")
    if nba:
        story.append(Paragraph(f"<b>NBA Compliance Note:</b>  {nba}", styles["Body10"]))

    doc.build(story)
    logger.info(f"OBE report PDF generated: {filepath}")
    return filepath


# ── Full Bundle (ZIP) ─────────────────────────────────────────────────────────

async def generate_course_bundle(course: Any) -> str:
    """
    Generate all PDFs for a course and zip them.
    Returns the absolute path to the ZIP file.
    """
    bundle_id  = str(uuid.uuid4())[:8]
    bundle_dir = PDF_OUTPUT_DIR / f"bundle_{bundle_id}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    files: List[str] = []

    # 1. Syllabus
    try:
        p = await generate_syllabus_pdf(course,
            output_filename=str(bundle_dir / "01_syllabus.pdf"))
        files.append(p)
    except Exception as e:
        logger.error(f"Bundle: syllabus failed: {e}")

    # 2. Question papers (one per assessment)
    assessment_data = course.assessment_data or {}
    assessments = assessment_data.get("assessments", [])
    for i, asmt in enumerate(assessments, 1):
        try:
            p = await generate_question_paper_pdf(
                asmt, course_title=course.title,
                output_filename=str(bundle_dir / f"02_{i:02d}_{asmt.get('type','qpaper').lower().replace(' ','_')}.pdf"),
            )
            files.append(p)
        except Exception as e:
            logger.error(f"Bundle: question paper {i} failed: {e}")

    # 3. OBE Report
    try:
        p = await generate_obe_report_pdf(
            course.obe_data or {}, course_title=course.title,
            output_filename=str(bundle_dir / "03_obe_report.pdf"),
        )
        files.append(p)
    except Exception as e:
        logger.error(f"Bundle: OBE report failed: {e}")

    # 4. Zip everything
    zip_path = str(PDF_OUTPUT_DIR / f"bundle_{bundle_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            zf.write(fp, arcname=Path(fp).name)

    # Cleanup temp dir
    import shutil
    shutil.rmtree(bundle_dir, ignore_errors=True)

    logger.info(f"Bundle ZIP generated: {zip_path} ({len(files)} files)")
    return zip_path


# ── Utility ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
