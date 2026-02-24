"""General helper functions."""

import uuid
import hashlib
import re
from typing import Any, Dict, Optional
from datetime import datetime


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def generate_workflow_id(prefix: str = "wf") -> str:
    """Generate a workflow ID with prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def hash_string(value: str) -> str:
    """Hash a string with SHA-256."""
    return hashlib.sha256(value.encode()).hexdigest()


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text


def truncate_text(text: str, max_length: int = 500, ellipsis: str = "...") -> str:
    """Truncate text to max_length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(ellipsis)] + ellipsis


def safe_get(obj: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get nested dict value."""
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
    return obj


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    filename = re.sub(r"[^\w\s.-]", "", filename)
    filename = re.sub(r"\s+", "_", filename)
    return filename[:255]


def parse_bloom_level(outcome: str) -> str:
    """Detect Bloom's taxonomy level from a learning outcome."""
    outcome_lower = outcome.lower()
    bloom_verbs = {
        "create": ["create", "design", "build", "compose", "develop", "formulate"],
        "evaluate": ["evaluate", "judge", "critique", "assess", "justify", "argue"],
        "analyze": ["analyze", "differentiate", "examine", "compare", "distinguish"],
        "apply": ["apply", "use", "implement", "execute", "solve", "demonstrate"],
        "understand": ["explain", "describe", "summarize", "classify", "interpret"],
        "remember": ["recall", "list", "define", "identify", "name", "state"],
    }
    for level, verbs in bloom_verbs.items():
        if any(verb in outcome_lower for verb in verbs):
            return level
    return "understand"


def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def now_iso() -> str:
    """Return current UTC datetime as ISO string."""
    return datetime.utcnow().isoformat() + "Z"