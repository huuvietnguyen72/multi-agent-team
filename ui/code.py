"""Dữ liệu cho khung "Mã nguồn": các bản đầu ra của dự án (output/ và output_history/), cây file, nội dung file.
Không phụ thuộc Chainlit."""
from __future__ import annotations

from pathlib import Path

from tools.run import output_run_id

SKIP_DIRS = {"node_modules", "target", "build", "dist", ".git", "__pycache__", ".idea", ".vscode", ".gradle"}
MAX_FILES = 2000
MAX_VIEW_CHARS = 200_000
LANGUAGES = {".py": "python", ".java": "java", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
             ".tsx": "typescript", ".html": "html", ".css": "css", ".json": "json", ".md": "markdown",
             ".xml": "xml", ".yml": "yaml", ".yaml": "yaml", ".sql": "sql", ".sh": "bash", ".properties": "ini",
             ".toml": "toml", ".txt": "text"}


def sources(out_dir: Path) -> list[dict]:
    """Các bản đầu ra xem được, mới nhất trước: {"id", "label", "path"}. id "output" là thư mục output/ hiện tại."""
    out_dir = Path(out_dir)
    items = []
    if out_dir.is_dir():
        current = output_run_id(out_dir)
        items.append({"id": "output", "label": f"Lượt {current} (mới nhất)" if current else "output/ (mới nhất)",
                      "path": out_dir, "run_id": current})
    history = out_dir.parent / "output_history"
    if history.is_dir():
        for d in sorted((p for p in history.iterdir() if p.is_dir()), reverse=True):
            label = f"Trước lượt {d.name[6:]}" if d.name.startswith("truoc-") else f"Lượt {d.name}"
            items.append({"id": d.name, "label": label, "path": d, "run_id": d.name})
    return items


def source_for_run(out_dir: Path, run_id: str | None) -> str:
    """id của bản đầu ra do lượt `run_id` ghi: output/ nếu đó là lượt mới nhất, không thì thư mục trong
    output_history/. Không còn (đã bị xóa bớt) thì trả về bản mới nhất."""
    items = sources(out_dir)
    for s in items:
        if run_id and s["run_id"] == run_id:
            return s["id"]
    return items[0]["id"] if items else "output"


def source_root(out_dir: Path, source_id: str) -> Path | None:
    return next((s["path"] for s in sources(out_dir) if s["id"] == source_id), None)


def tree(root: Path) -> tuple[list[dict], bool]:
    """([{"path": "backend/src/.../X.java", "size": 123}], bị cắt bớt). Bỏ qua node_modules, target, ..."""
    root = Path(root)
    if not root.is_dir():
        return [], False
    files: list[dict] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or not p.is_file():
            continue
        files.append({"path": rel.as_posix(), "size": p.stat().st_size})
        if len(files) >= MAX_FILES:
            return files, True
    return files, False


def language(path: str) -> str:
    return LANGUAGES.get(Path(path).suffix.lower(), "text")


def read_file(root: Path, rel: str) -> tuple[str, str] | None:
    """(nội dung, ngôn ngữ) của file `rel` trong `root`. None nếu đường dẫn ra ngoài root hoặc không đọc được."""
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "(file nhị phân, không hiển thị)", "text"
    except OSError:
        return None
    if len(text) > MAX_VIEW_CHARS:
        text = text[:MAX_VIEW_CHARS] + "\n\n(đã cắt bớt)"
    return text, language(rel)
