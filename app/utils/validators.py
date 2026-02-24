"""Input validation utilities."""

import re
from typing import List
from app.utils.exceptions import ValidationError


def validate_email(email: str) -> str:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(pattern, email):
        raise ValidationError("Invalid email address", field="email")
    return email.lower().strip()


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters", field="password")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter", field="password")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter", field="password")
    if not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one digit", field="password")
    return password


def validate_course_credits(credits: int) -> int:
    if credits < 1 or credits > 6:
        raise ValidationError("Credits must be between 1 and 6", field="credits")
    return credits


def validate_semester(semester: int) -> int:
    if semester < 1 or semester > 8:
        raise ValidationError("Semester must be between 1 and 8", field="semester")
    return semester


def validate_file_extension(filename: str, allowed: List[str]) -> bool:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed:
        raise ValidationError(f"File type not allowed. Allowed: {', '.join(allowed)}", field="file")
    return True