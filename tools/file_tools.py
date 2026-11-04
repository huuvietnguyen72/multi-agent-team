"""Tool ghi/đọc file cho agent. Chỉ ghi được bên trong <output>/<role>/ và <output>/docs/.

Thư mục output lấy từ biến môi trường OUTPUT_DIR (main.py đặt thành projects/<tên>/output);
thiếu thì dùng output/ ở gốc repo.
"""
from __future__ import annotations

import os
from pathlib import Path

from tools.runlog import progress

ROOT = Path(__file__).resolve().parent.parent


def output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR") or ROOT / "output").resolve()


def display(path: Path) -> str:
    """Đường dẫn để ghi vào state/log: tương đối với gốc repo nếu nằm trong repo, ngược lại là tuyệt đối."""
    path = path.resolve()
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def write_files(role_dir: str, files: list[dict]) -> list[str]:
    progress("write")
    base = (output_dir() / role_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    written = []
    for f in files:
        target = (base / f["path"]).resolve()
        if not target.is_relative_to(base):
            raise ValueError(f"Đường dẫn ngoài phạm vi: {f['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
        written.append(display(target))
    return written


def write_doc(name: str, content: str) -> str:
    progress("write")
    target = output_dir() / "docs" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return display(target)


def read_files(paths: list[str], limit_chars: int = 150_000) -> str:
    """Ghép nội dung các file để đưa cho Reviewer, Tester, hoặc Dev khi sửa."""
    if paths:
        progress("read")
    chunks, total = [], 0
    for p in paths:
        fp = Path(p) if Path(p).is_absolute() else ROOT / p
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
