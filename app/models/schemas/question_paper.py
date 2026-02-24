"""
Question Paper Schema — Exam type definitions, request/response models.
Supports: CIA-1, CIA-2, Model Exam, End Semester, Lab Record, Assignment
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class ExamType(str, Enum):
    CIA1        = "CIA-1"
    CIA2        = "CIA-2"
    MODEL_EXAM  = "Model Exam"
    END_SEM     = "End Semester"
    LAB_RECORD  = "Lab Record"
    ASSIGNMENT  = "Assignment"
    QUIZ        = "Quiz"
    VIVA        = "Viva"


class DifficultyLevel(str, Enum):
    EASY   = "easy"
    MEDIUM = "medium"
    HARD   = "hard"
    MIXED  = "mixed"


class ExportFormat(str, Enum):
    PDF  = "pdf"
    HTML = "html"


# ── Per exam-type defaults ─────────────────────────────────────────────────────
EXAM_DEFAULTS: Dict[str, Dict] = {
    "CIA-1": {
        "duration_minutes": 90,
        "total_marks": 50,
        "instructions": (
            "Answer all questions. Part A carries 2 marks each, "
            "Part B carries 8 marks each."
        ),
        "parts": [
            {"label": "Part A", "type": "Short Answer",  "num_questions": 10, "marks_each": 2},
            {"label": "Part B", "type": "Descriptive",   "num_questions": 5,  "marks_each": 8, "choose": 4},
        ],
        "modules_covered": "Module 1-2",
    },
    "CIA-2": {
        "duration_minutes": 90,
        "total_marks": 50,
        "instructions": (
            "Answer all questions. Part A carries 2 marks each, "
            "Part B carries 8 marks each."
        ),
        "parts": [
            {"label": "Part A", "type": "Short Answer",  "num_questions": 10, "marks_each": 2},
            {"label": "Part B", "type": "Descriptive",   "num_questions": 5,  "marks_each": 8, "choose": 4},
        ],
        "modules_covered": "Module 3-4",
    },
    "Model Exam": {
        "duration_minutes": 180,
        "total_marks": 100,
        "instructions": (
            "Answer all questions. Part A carries 2 marks each. "
            "Part B: 5 questions × 16 marks (answer any 4). "
            "Part C: 1 compulsory question − 20 marks."
        ),
        "parts": [
            {"label": "Part A", "type": "MCQ / Short",        "num_questions": 10, "marks_each": 2},
            {"label": "Part B", "type": "Long Answer",        "num_questions": 5,  "marks_each": 16, "choose": 4},
            {"label": "Part C", "type": "Case Study / Design","num_questions": 1,  "marks_each": 20},
        ],
        "modules_covered": "All Modules",
    },
    "End Semester": {
        "duration_minutes": 180,
        "total_marks": 100,
        "instructions": (
            "Answer all questions. Part A: 10 questions × 2 = 20 marks. "
            "Part B: 5 questions × 16 marks (either/or). "
            "Part C: 1 compulsory problem − 20 marks."
        ),
        "parts": [
            {"label": "Part A", "type": "Short Answer / MCQ", "num_questions": 10, "marks_each": 2},
            {"label": "Part B", "type": "Long Answer",        "num_questions": 5,  "marks_each": 16, "either_or": True},
            {"label": "Part C", "type": "Compulsory Problem", "num_questions": 1,  "marks_each": 20},
        ],
        "modules_covered": "All Modules (1–5)",
    },
    "Lab Record": {
        "duration_minutes": 180,
        "total_marks": 100,
        "instructions": (
            "Perform the given experiment. Submit the written record "
            "and demonstrate the output to the examiner."
        ),
        "parts": [
            {"label": "Experiment", "type": "Lab Exercise",  "num_questions": 1,  "marks_each": 60},
            {"label": "Viva",       "type": "Oral Questions","num_questions": 5,  "marks_each": 8},
        ],
        "modules_covered": "All Lab Experiments",
    },
    "Quiz": {
        "duration_minutes": 30,
        "total_marks": 20,
        "instructions": "Answer all questions. Each question carries 2 marks.",
        "parts": [
            {"label": "Section A", "type": "MCQ",         "num_questions": 10, "marks_each": 2},
        ],
        "modules_covered": "Module 1",
    },
}


class QuestionPaperRequest(BaseModel):
    """Request body for generating a question paper."""

    course_id:          str     = Field(..., description="Course UUID from the courses table")
    exam_type:          ExamType = Field(..., description="CIA-1, CIA-2, Model Exam, End Semester, Lab Record, Quiz, Viva, Assignment")

    # Optional overrides (defaults computed from exam_type if omitted)
    department:         Optional[str]  = None
    institution_name:   Optional[str]  = "My Institution"
    academic_year:      Optional[str]  = None
    subject_code:       Optional[str]  = None
    modules_covered:    Optional[str]  = None
    duration_minutes:   Optional[int]  = None
    total_marks:        Optional[int]  = None
    instructions:       Optional[str]  = None
    difficulty:         DifficultyLevel = DifficultyLevel.MIXED
    additional_context: Optional[str]  = None   # e.g. "focus on unit 2 topics"

    # Export format
    export_format: ExportFormat = ExportFormat.PDF


class GeneratedQuestion(BaseModel):
    question:    str
    bloom_level: str
    marks:       int
    answer_hint: Optional[str] = None
    options:     Optional[List[str]] = None   # for MCQ


class GeneratedSection(BaseModel):
    label:     str
    type:      str
    marks_each:int
    choose:    Optional[int] = None
    either_or: bool = False
    questions: List[GeneratedQuestion] = []


class QuestionPaperResponse(BaseModel):
    paper_id:         str
    course_id:        str
    course_title:     str
    exam_type:        str
    institution_name: str
    department:       str
    subject_code:     Optional[str]
    academic_year:    Optional[str]
    duration_minutes: int
    total_marks:      int
    modules_covered:  str
    instructions:     str
    sections:         List[GeneratedSection]
    generated_at:     str
    export_url:       str     # URL to download the file
    export_format:    str
