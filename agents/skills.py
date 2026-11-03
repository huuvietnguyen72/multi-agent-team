"""Đọc skills/<role>/SKILL.md, dùng làm system prompt của role."""
from __future__ import annotations

from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"


def skill_path(role: str) -> Path:
    return SKILLS / role / "SKILL.md"


def load_skill(role: str) -> str:
    """Nội dung SKILL.md đã bỏ frontmatter (name, description)."""
    text = skill_path(role).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.lstrip()
