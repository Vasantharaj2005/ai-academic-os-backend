"""
Question Paper PDF & HTML Renderer
Generates exam-quality output with university header, per-section formatting,
either/or choices, Bloom's labels, and answer hint toggle.
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)

# ── Output dir ──────────────────────────────────────────────────────────────────
PAPER_DIR = Path("generated_pdfs") / "question_papers"
PAPER_DIR.mkdir(parents=True, exist_ok=True)

# ── Colour palette ─────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1e3a8a")
STEEL  = colors.HexColor("#334155")
SLATE  = colors.HexColor("#64748b")
LIGHT  = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#cbd5e1")
WHITE  = colors.white


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _styles():
    base = getSampleStyleSheet()
    extra = [
        ParagraphStyle("QP_Title",    parent=base["Normal"], fontSize=14,
                       alignment=TA_CENTER, fontName="Helvetica-Bold",
                       textColor=NAVY, spaceAfter=2),
        ParagraphStyle("QP_Sub",      parent=base["Normal"], fontSize=11,
                       alignment=TA_CENTER, fontName="Helvetica", spaceAfter=2),
        ParagraphStyle("QP_Meta",     parent=base["Normal"], fontSize=9,
                       alignment=TA_CENTER, textColor=STEEL),
        ParagraphStyle("QP_Section",  parent=base["Normal"], fontSize=11,
                       fontName="Helvetica-Bold", textColor=NAVY,
                       spaceBefore=10, spaceAfter=4),
        ParagraphStyle("QP_Question", parent=base["Normal"], fontSize=10,
                       leading=14, spaceAfter=2),
        ParagraphStyle("QP_Option",   parent=base["Normal"], fontSize=10,
                       leftIndent=24, spaceAfter=1),
        ParagraphStyle("QP_Bloom",    parent=base["Normal"], fontSize=8,
                       textColor=SLATE, leftIndent=12, spaceAfter=6),
        ParagraphStyle("QP_Hint",     parent=base["Normal"], fontSize=8,
                       textColor=colors.HexColor("#0f766e"),
                       leftIndent=12, spaceAfter=6),
    ]
    for s in extra:
        base.add(s)
    return base


# ────────────────────────────────────────────────────────────────────────────────
# PDF generator
# ────────────────────────────────────────────────────────────────────────────────

async def render_question_paper_pdf(
    paper_data: Dict[str, Any],
    include_answer_hints: bool = False,
    output_filename: Optional[str] = None,
) -> str:
    """
    Render a fully formatted question-paper PDF.
    `paper_data` is the merged dict: request fields + AI-generated sections.
    Returns the absolute path of the generated file.
    """
    st = _styles()
    fid = output_filename or f"qpaper_{_ts()}_{uuid.uuid4().hex[:6]}.pdf"
    filepath = str(PAPER_DIR / fid)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"{paper_data.get('exam_type','')} — {paper_data.get('course_title','')}",
        author="AI Academic OS",
    )
    story = []

    # ── University / Institution Header ────────────────────────────────────────
    institution = paper_data.get("institution_name", "My Institution")
    course_title = paper_data.get("course_title", "")
    exam_type    = paper_data.get("exam_type", "")
    dept         = paper_data.get("department", "")
    sub_code     = paper_data.get("subject_code", "")
    duration     = paper_data.get("duration_minutes", 0)
    total_marks  = paper_data.get("total_marks", 0)
    modules      = paper_data.get("modules_covered", "")
    acad_year    = paper_data.get("academic_year", datetime.now().strftime("%Y-%m"))
    instructions = paper_data.get("instructions", "Answer all questions.")

    story.append(Paragraph(institution.upper(), st["QP_Title"]))
    story.append(Paragraph(f"Department of {dept}", st["QP_Sub"]))
    story.append(Paragraph(exam_type.upper() + " EXAMINATION", st["QP_Sub"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=4))

    # Meta block (2 columns)
    meta_rows = [
        [
            Paragraph(f"<b>Subject:</b> {course_title}" + (f" ({sub_code})" if sub_code else ""), st["QP_Meta"]),
            Paragraph(f"<b>Academic Year:</b> {acad_year}", st["QP_Meta"]),
        ],
        [
            Paragraph(f"<b>Modules Covered:</b> {modules}", st["QP_Meta"]),
            Paragraph(f"<b>Duration:</b> {duration} minutes", st["QP_Meta"]),
        ],
        [
            Paragraph(f"<b>Date:</b> ___________________", st["QP_Meta"]),
            Paragraph(f"<b>Max. Marks:</b> {total_marks}", st["QP_Meta"]),
        ],
        [
            Paragraph("<b>Reg. No.:</b> ___________________", st["QP_Meta"]),
            Paragraph("<b>Roll No.:</b> ___________________", st["QP_Meta"]),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[3.5 * inch, 3.5 * inch])
    meta_table.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    story.append(Paragraph(f"<i>Instructions: {instructions}</i>", st["QP_Meta"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=8))

    # ── Sections ───────────────────────────────────────────────────────────────
    for section in paper_data.get("sections", []):
        label      = section.get("label", "")
        qtype      = section.get("type", "")
        marks_each = section.get("marks_each", 0)
        choose     = section.get("choose")
        either_or  = section.get("either_or", False)
        questions  = section.get("questions", [])

        # Section header
        choose_note = f"  (Answer any {choose})" if choose else ""
        eo_note     = "  (Either or)" if either_or else ""
        story.append(Paragraph(
            f"{label} — {qtype}   [{marks_each} marks each]{choose_note}{eo_note}",
            st["QP_Section"],
        ))

        for qi, q in enumerate(questions, 1):
            q_txt     = q.get("question", "")
            bloom     = q.get("bloom_level", "").capitalize()
            hint      = q.get("answer_hint", "")
            options   = q.get("options") or []
            q_marks   = q.get("marks", marks_each)

            # Either/or: every 2 questions share a number with (a)/(b)
            if either_or:
                if qi % 2 == 1:
                    story.append(Paragraph(
                        f"<b>{(qi + 1) // 2}.</b>  (a)  {q_txt}   [{q_marks} M]",
                        st["QP_Question"],
                    ))
                else:
                    story.append(Paragraph(f"<b>       (b)</b>  {q_txt}   [{q_marks} M]", st["QP_Question"]))
            else:
                story.append(Paragraph(
                    f"<b>{qi}.</b>  {q_txt}   [{q_marks} M]",
                    st["QP_Question"],
                ))

            for opt in options:
                story.append(Paragraph(opt, st["QP_Option"]))

            meta_line = f"[CO: —  |  Bloom's: {bloom}]"
            story.append(Paragraph(meta_line, st["QP_Bloom"]))

            if include_answer_hints and hint:
                story.append(Paragraph(f"<i>Key: {hint}</i>", st["QP_Hint"]))

        story.append(Spacer(1, 6))

    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    story.append(Paragraph("- - - End of Question Paper - - -",
        ParagraphStyle("End", parent=st["QP_Meta"], alignment=TA_CENTER, textColor=SLATE)))

    doc.build(story)
    return filepath


# ────────────────────────────────────────────────────────────────────────────────
# HTML generator (self-contained, print-ready)
# ────────────────────────────────────────────────────────────────────────────────

async def render_question_paper_html(
    paper_data: Dict[str, Any],
    include_answer_hints: bool = False,
    output_filename: Optional[str] = None,
) -> str:
    """
    Render a print-ready, self-contained HTML question paper.
    Returns the absolute path of the generated .html file.
    """
    fid = output_filename or f"qpaper_{_ts()}_{uuid.uuid4().hex[:6]}.html"
    filepath = str(PAPER_DIR / fid)

    institution  = paper_data.get("institution_name", "My Institution")
    course_title = paper_data.get("course_title", "")
    exam_type    = paper_data.get("exam_type", "")
    dept         = paper_data.get("department", "")
    sub_code     = paper_data.get("subject_code", "")
    duration     = paper_data.get("duration_minutes", 0)
    total_marks  = paper_data.get("total_marks", 0)
    modules      = paper_data.get("modules_covered", "")
    acad_year    = paper_data.get("academic_year", "")
    instructions = paper_data.get("instructions", "Answer all questions.")

    # Build sections HTML
    sections_html = ""
    for section in paper_data.get("sections", []):
        label      = section.get("label", "")
        qtype      = section.get("type", "")
        marks_each = section.get("marks_each", 0)
        choose     = section.get("choose")
        either_or  = section.get("either_or", False)
        questions  = section.get("questions", [])

        choose_note = f" (Answer any {choose})" if choose else ""
        eo_note     = " (Either or)" if either_or else ""
        sections_html += f"""
        <div class="section">
          <div class="section-header">
            {label} &mdash; {qtype} [{marks_each} marks each]{choose_note}{eo_note}
          </div>
          <ol class="questions">
        """
        for qi, q in enumerate(questions, 1):
            q_txt   = q.get("question", "")
            bloom   = q.get("bloom_level", "").capitalize()
            hint    = q.get("answer_hint", "")
            options = q.get("options") or []
            q_marks = q.get("marks", marks_each)

            hint_html = ""
            if include_answer_hints and hint:
                hint_html = f'<div class="hint">Key: {hint}</div>'

            options_html = ""
            if options:
                options_html = "<ul class='options'>" + "".join(
                    f"<li>{opt}</li>" for opt in options
                ) + "</ul>"

            if either_or and qi % 2 == 0:
                sections_html += f"""
                <li class="or-marker" value="{qi}">(b) {q_txt} [{q_marks} M]
                  {options_html}
                  <span class="bloom">Bloom&apos;s: {bloom}</span>
                  {hint_html}
                </li>"""
            else:
                num = (qi + 1) // 2 if either_or else qi
                prefix = "(a)" if either_or else ""
                sections_html += f"""
                <li value="{num}">{prefix} {q_txt} [{q_marks} M]
                  {options_html}
                  <span class="bloom">Bloom&apos;s: {bloom}</span>
                  {hint_html}
                </li>"""

        sections_html += "</ol></div>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{exam_type} — {course_title}</title>
  <style>
    @page {{ size: A4; margin: 18mm; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Times New Roman', serif; font-size: 11pt; color: #1e293b; }}
    .header {{ text-align: center; border-bottom: 2px solid #1e3a8a; padding-bottom: 8px; margin-bottom: 8px; }}
    .header h1 {{ font-size: 14pt; color: #1e3a8a; text-transform: uppercase; }}
    .header h2 {{ font-size: 11pt; font-weight: normal; color: #334155; }}
    .meta-table {{ width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 10pt; }}
    .meta-table td {{ padding: 3px 6px; }}
    .sep {{ border: none; border-top: 1px solid #cbd5e1; margin: 6px 0; }}
    .instructions {{ font-style: italic; font-size: 9.5pt; color: #475569; margin: 4px 0 10px; }}
    .section {{ margin-bottom: 14px; }}
    .section-header {{ font-weight: bold; font-size: 11pt; color: #1e3a8a;
                       border-bottom: 1px solid #cbd5e1; padding-bottom: 3px; margin-bottom: 6px; }}
    ol.questions {{ list-style-type: decimal; padding-left: 22px; }}
    ol.questions li {{ margin-bottom: 8px; line-height: 1.5; }}
    li.or-marker {{ list-style-type: none; padding-left: 4px; border-top: 1px dotted #cbd5e1;
                    margin-top: 4px; padding-top: 4px; }}
    ul.options {{ list-style-type: lower-alpha; padding-left: 28px; margin: 4px 0; }}
    .bloom {{ font-size: 8pt; color: #64748b; display: block; }}
    .hint {{ font-size: 8.5pt; color: #0f766e; font-style: italic; margin-top: 2px; }}
    .footer {{ text-align: center; color: #94a3b8; font-size: 9pt; margin-top: 14px;
               border-top: 1px solid #cbd5e1; padding-top: 6px; }}
    @media print {{
      .hint {{ display: {'block' if include_answer_hints else 'none'}; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>{institution}</h1>
    <h2>Department of {dept}</h2>
    <h2>{exam_type.upper()} EXAMINATION</h2>
  </div>
  <table class="meta-table">
    <tr>
      <td><strong>Subject:</strong> {course_title}{f' ({sub_code})' if sub_code else ''}</td>
      <td><strong>Academic Year:</strong> {acad_year}</td>
    </tr>
    <tr>
      <td><strong>Modules Covered:</strong> {modules}</td>
      <td><strong>Duration:</strong> {duration} minutes</td>
    </tr>
    <tr>
      <td><strong>Date:</strong> ___________________</td>
      <td><strong>Max. Marks:</strong> {total_marks}</td>
    </tr>
    <tr>
      <td><strong>Reg. No.:</strong> ___________________</td>
      <td><strong>Roll No.:</strong> ___________________</td>
    </tr>
  </table>
  <hr class="sep">
  <div class="instructions">Instructions: {instructions}</div>
  <hr class="sep">

  {sections_html}

  <div class="footer">- - - End of Question Paper - - -</div>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath
