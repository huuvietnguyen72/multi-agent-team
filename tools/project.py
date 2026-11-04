"""Đọc một dự án trong projects/<tên>/.

Mỗi dự án là một thư mục:
  project.toml      tên dự án, đường dẫn requirements/stack, lệnh chạy test (xem projects/_template/)
  requirements.md   đề bài: chức năng F1..Fn, business rules BR-xx, ràng buộc
  stack.md          stack và quy ước kỹ thuật; được chèn vào đầu prompt của mọi agent
  output/           code và tài liệu agent sinh ra (không commit)
Thư mục bắt đầu bằng "_" (như _template) là mẫu, không hiện trong danh sách dự án.
"""
from __future__ import annotations

import json
import re
import tomllib
import unicodedata
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


def slugify(text: str) -> str:
    """'Quản lý kho' -> 'quan-ly-kho'."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "du-an"


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # chuỗi JSON cũng là chuỗi TOML hợp lệ


def write_project(name: str, *, title: str, requirements: str, stack: str, test_command: str = "",
                  test_cwd: str = "backend", base: Path | None = None, create: bool = False) -> Project:
    """Ghi projects/<name>/ (project.toml, requirements.md, stack.md). create=True: báo lỗi nếu đã có.
    Sửa dự án có sẵn thì giữ nguyên các khóa khác trong project.toml (output, timeout...)."""
    base = base or PROJECTS
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", name or ""):
        raise ValueError("Tên thư mục chỉ gồm chữ thường không dấu, số và gạch nối")
    d = base / name
    toml_path = d / "project.toml"
    if create and d.exists():
        raise FileExistsError(f"Đã có dự án '{name}', chọn tên thư mục khác")
    if not title.strip() or not requirements.strip() or not stack.strip():
        raise ValueError("Tên dự án, requirements và stack không được trống")
    cfg = tomllib.loads(toml_path.read_text(encoding="utf-8")) if toml_path.is_file() else {}
    d.mkdir(parents=True, exist_ok=True)
    req_name, stack_name = cfg.get("requirements", "requirements.md"), cfg.get("stack", "stack.md")
    (d / req_name).write_text(requirements.rstrip() + "\n", encoding="utf-8")
    (d / stack_name).write_text(stack.rstrip() + "\n", encoding="utf-8")
    tests = {**(cfg.get("tests") or {}), "command": test_command.strip(),
             "cwd": (cfg.get("tests") or {}).get("cwd", test_cwd)}
    lines = [f"name = {_toml_str(title.strip())}", f"requirements = {_toml_str(req_name)}",
             f"stack = {_toml_str(stack_name)}"]
    lines += [f"{k} = {_toml_str(v) if isinstance(v, str) else json.dumps(v)}" for k, v in cfg.items()
              if k not in ("name", "requirements", "stack", "tests") and isinstance(v, (str, int, float, bool))]
    lines += ["", "[tests]", "# Chạy khi RUN_TESTS=1; cwd tính từ thư mục output của dự án"]
    lines += [f"{k} = {_toml_str(v) if isinstance(v, str) else json.dumps(v)}" for k, v in tests.items()
              if isinstance(v, (str, int, float, bool))]
    toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return load_project(name, base=base)


# ---------- module: mỗi module là một file projects/<dự án>/modules/<tên>.md, chạy riêng trong một cuộc chat ----------

MODULES = "modules"


@dataclass(frozen=True)
class Module:
    name: str           # tên file, không có .md
    title: str          # dòng tiêu đề "# ..." đầu file
    path: Path
    requirements: str


def _module_title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    title = m.group(1).strip() if m else fallback
    return re.sub(r"^module\s*[:\-·]\s*", "", title, flags=re.IGNORECASE) or fallback


def list_modules(project: str, base: Path | None = None) -> list[Module]:
    d = (base or PROJECTS) / project / MODULES
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        out.append(Module(name=p.stem, title=_module_title(text, p.stem), path=p, requirements=text))
    return out


def load_module(project: str, name: str, base: Path | None = None) -> Module:
    for m in list_modules(project, base):
        if m.name == name:
            return m
    raise FileNotFoundError(f"Dự án '{project}' không có module '{name}' ({MODULES}/{name}.md)")


def write_module(project: str, name: str, *, title: str, requirements: str, base: Path | None = None,
                 create: bool = False) -> Module:
    """Ghi projects/<project>/modules/<name>.md. Dòng đầu luôn là "# Module: <title>"."""
    base = base or PROJECTS
    if not (base / project / "project.toml").is_file():
        raise FileNotFoundError(f"Không có dự án '{project}'")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", name or ""):
        raise ValueError("Tên file module chỉ gồm chữ thường không dấu, số và gạch nối")
    if not title.strip() or not requirements.strip():
        raise ValueError("Tên module và yêu cầu không được trống")
    path = base / project / MODULES / f"{name}.md"
    if create and path.exists():
        raise FileExistsError(f"Đã có module '{name}', chọn tên khác")
    body = re.sub(r"\A\s*#\s+.*\n", "", requirements.strip() + "\n", count=1).lstrip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Module: {title.strip()}\n\n{body}", encoding="utf-8")
    return load_module(project, name, base)


def module_requirements(project: Project, module: Module) -> str:
    """Requirements đưa cho team khi chạy một module: yêu cầu của module trước, yêu cầu chung của dự án sau
    (để giữ business rule và bối cảnh)."""
    return (f"{module.requirements.strip()}\n\n---\n\n"
            f"# Bối cảnh: yêu cầu chung của dự án {project.title}\n\n"
            "(Chỉ để tham khảo business rule và phần đã có; lượt này chỉ làm module ở trên.)\n\n"
            f"{project.requirements.strip()}\n")
