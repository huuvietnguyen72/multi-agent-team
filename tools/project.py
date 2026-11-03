"""Đọc một dự án trong projects/<tên>/.

Mỗi dự án là một thư mục:
  project.toml      tên dự án, đường dẫn requirements/stack, lệnh chạy test (xem projects/_template/)
  requirements.md   đề bài: chức năng F1..Fn, business rules BR-xx, ràng buộc
  stack.md          stack và quy ước kỹ thuật; được chèn vào đầu prompt của mọi agent
  output/           code và tài liệu agent sinh ra (không commit)
Thư mục bắt đầu bằng "_" (như _template) là mẫu, không hiện trong danh sách dự án.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"


@dataclass(frozen=True)
class Project:
    name: str                    # tên thư mục trong projects/
    title: str
    dir: Path
    requirements: str            # nội dung requirements
    requirements_path: Path
    stack: str                   # nội dung stack.md
    output_dir: Path
    test_command: str | None     # lệnh test tự động, chạy khi RUN_TESTS=1
    test_cwd: str                # thư mục chạy lệnh test, tính từ output_dir
    test_timeout: int


def list_projects(base: Path | None = None) -> list[str]:
    base = base or PROJECTS
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir()
                  if (p / "project.toml").is_file() and not p.name.startswith("_"))


def load_project(name: str, requirements: str | Path | None = None, base: Path | None = None) -> Project:
    """Đọc projects/<name>/. `requirements` (tùy chọn) thay cho file requirements trong project.toml,
    ví dụ để chạy riêng một module của dự án."""
    base = base or PROJECTS
    d = base / name
    toml_path = d / "project.toml"
    if not toml_path.is_file():
        have = ", ".join(list_projects(base)) or "(chưa có)"
        raise FileNotFoundError(f"Không có dự án '{name}' ({toml_path} không tồn tại). Các dự án hiện có: {have}")
    cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    req_path = Path(requirements) if requirements else d / cfg.get("requirements", "requirements.md")
    if not req_path.is_absolute() and requirements:
        req_path = (ROOT / req_path) if (ROOT / req_path).exists() else (d / req_path)
    stack_path = d / cfg.get("stack", "stack.md")
    for p, what in ((req_path, "requirements"), (stack_path, "stack")):
        if not p.is_file():
            raise FileNotFoundError(f"Dự án '{name}': thiếu file {what} {p}")

    tests = cfg.get("tests") or {}
    return Project(
        name=name,
        title=cfg.get("name", name),
        dir=d,
        requirements=req_path.read_text(encoding="utf-8"),
        requirements_path=req_path,
        stack=stack_path.read_text(encoding="utf-8"),
        output_dir=(d / cfg.get("output", "output")).resolve(),
        test_command=tests.get("command") or None,
        test_cwd=tests.get("cwd", "."),
        test_timeout=int(tests.get("timeout", 600)),
    )
