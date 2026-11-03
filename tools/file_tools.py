"""Tool ghi/đọc file cho agent. Chỉ ghi được bên trong output/<role>/."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"


def write_files(role_dir: str, files: list[dict]) -> list[str]:
    base = (OUTPUT / role_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    written = []
    for f in files:
        target = (base / f["path"]).resolve()
        if not target.is_relative_to(base):
            raise ValueError(f"Đường dẫn ngoài phạm vi: {f['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
        written.append(str(target.relative_to(ROOT)).replace("\\", "/"))
    return written


def write_doc(name: str, content: str) -> str:
    target = OUTPUT / "docs" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target.relative_to(ROOT)).replace("\\", "/")


def read_files(paths: list[str], limit_chars: int = 150_000) -> str:
    """Ghép nội dung các file để đưa cho Tester đọc."""
    chunks, total = [], 0
    for p in paths:
        fp = ROOT / p
        if not fp.exists():
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        chunk = f"\n----- {p} -----\n{text}"
        if total + len(chunk) > limit_chars:
            chunks.append(f"\n----- {p} ----- (bỏ qua: vượt giới hạn độ dài)")
            continue
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks)
