"""Dự án trên giao diện, giống Project của Claude: mỗi dự án là một mục trong ô chọn ở góc trên, có trang
tổng quan (mô tả, các lượt đã chạy, các cuộc chat của dự án) và nút tạo dự án mới từ một câu ý tưởng.
Không phụ thuộc Chainlit."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from agents.providers import adapter, load_providers, target_for
from schemas import ModuleDraft, ProjectDraft
from tools.run import existing_code
from tools.project import PROJECTS, list_modules, list_projects, load_project, slugify
from ui.history import DB_PATH, RUNS_DIR

MAX_LISTED = 8
MODULE_TAG = "module:"  # tag của cuộc chat thuộc một module: "module:<tên>", cạnh tag tên dự án


def template() -> tuple[str, str]:
    d = PROJECTS / "_template"
    return (d / "requirements.md").read_text(encoding="utf-8"), (d / "stack.md").read_text(encoding="utf-8")


def unique_slug(slug: str, base: Path = PROJECTS, suffix: str = "") -> str:
    """Tên chưa dùng trong `base` (`suffix` là đuôi file, ví dụ ".md" cho module)."""
    slug = slugify(slug)
    out, n = slug, 2
    while (base / f"{out}{suffix}").exists():
        out, n = f"{slug}-{n}", n + 1
    return out


def draft_project(idea: str, *, previous: dict | None = None, spec: str | None = None,
                  providers=None) -> tuple[ProjectDraft, str]:
    """(bản nháp, nhãn model) cho ý tưởng `idea`; `previous` là bản nháp trước khi người dùng yêu cầu sửa.
    Dùng model `spec` (mặc định model của PM); mock thì điền mẫu, không gọi model."""
    providers = providers if providers is not None else load_providers()
    target = target_for("setup", providers, spec=spec or target_for("pm", providers).label)
    req_t, stack_t = template()
    if target.provider.type == "mock":
        return mock_draft(idea, previous), target.label
    parts = [f"## Mẫu requirements.md\n\n{req_t}", f"## Mẫu stack.md\n\n{stack_t}"]
    if previous:
        parts.append("## Bản nháp hiện tại\n\n" + json.dumps(previous, ensure_ascii=False, indent=1))
        parts.append(f"## Người dùng yêu cầu sửa\n\n{idea}")
    else:
        parts.append(f"## Ý tưởng của người dùng\n\n{idea}")
    draft = adapter(target.provider.type)(target, "setup", "\n\n".join(parts), ProjectDraft)
    return draft, target.label


def mock_draft(idea: str, previous: dict | None = None) -> ProjectDraft:
    """Không gọi model: lấy mẫu, điền tên và mô tả từ ý tưởng. Người dùng tự viết chức năng và BR."""
    if previous:
        return ProjectDraft(**{**previous, "reply": "(mock) Không soạn lại được khi chạy mock; anh sửa trực tiếp "
                                                    "trong khung bên phải."})
    req_t, stack_t = template()
    title = re.split(r"[.:\n]", idea.strip(), maxsplit=1)[0].strip()[:60] or "Dự án mới"
    req = req_t.replace("<Tên hệ thống>", title).replace("<Hệ thống làm gì, cho ai, trong 1-2 câu.>", idea.strip())
    return ProjectDraft(title=title, slug=slugify(title), requirements=req, stack=stack_t, test_command="",
                        reply="(mock) Em điền mẫu với tên và mô tả của anh. Bật model thật (tắt mock ở bánh răng) "
                              "để PM soạn đầy đủ chức năng và business rule.")


MODULE_TEMPLATE = """## Mục tiêu

{idea}

## Chức năng

| Mã | Chức năng | Mô tả |
|---|---|---|
| F? | ... | ... |

## Business rules

| Mã | Quy tắc | Khi vi phạm |
|---|---|---|
| BR-? | ... | ... |

## Liên quan tới phần đã có

...

## Ngoài phạm vi

...

## Ví dụ kiểm thử mong đợi

...
"""


def draft_module(project: str, idea: str, *, previous: dict | None = None, spec: str | None = None,
                 providers=None) -> tuple[ModuleDraft, str]:
    """(bản nháp module, nhãn model) cho mô tả `idea` của người dùng, trong dự án `project`."""
    providers = providers if providers is not None else load_providers()
    target = target_for("module", providers, spec=spec or target_for("pm", providers).label)
    if target.provider.type == "mock":
        return mock_module(idea, previous), target.label
    p = load_project(project)
    have = "\n".join(f"- {m.title} (`{m.name}`)" for m in list_modules(project)) or "(chưa có)"
    code = existing_code(p.output_dir)
    files = [f for k in ("backend_code", "frontend_code") for f in code[k]]
    parts = [f"## Requirements chung của dự án {p.title}\n\n{p.requirements}", f"## Module đã có\n\n{have}",
             "## File code đang có\n\n" + ("\n".join(f"- {f}" for f in files[:200]) or "(chưa có code)")]
    if previous:
        parts.append("## Bản nháp hiện tại\n\n" + json.dumps(previous, ensure_ascii=False, indent=1))
        parts.append(f"## Người dùng yêu cầu sửa\n\n{idea}")
    else:
        parts.append(f"## Module người dùng muốn thêm\n\n{idea}")
    draft = adapter(target.provider.type)(target, "module", "\n\n".join(parts), ModuleDraft)
    return draft, target.label


def mock_module(idea: str, previous: dict | None = None) -> ModuleDraft:
    if previous:
        return ModuleDraft(**{**{k: previous.get(k, "") for k in ("title", "slug", "requirements")},
                              "reply": "(mock) Không soạn lại được khi chạy mock; anh sửa trực tiếp trong khung bên phải."})
    title = re.split(r"[.:\n]", idea.strip(), maxsplit=1)[0].strip()[:60] or "Module mới"
    return ModuleDraft(title=title, slug=slugify(title), requirements=MODULE_TEMPLATE.format(idea=idea.strip()),
                       reply="(mock) Em điền mẫu với mô tả của anh. Tắt mock để PM soạn đầy đủ chức năng và BR.")


def description(name: str, limit: int = 300) -> str:
    """Đoạn "Mô tả" trong requirements.md của dự án (hoặc đoạn văn đầu tiên)."""
    try:
        text = load_project(name).requirements
    except (FileNotFoundError, ValueError):
        return ""
    m = re.search(r"^##\s*Mô tả\s*\n+(.+?)(?:\n\s*\n|\n##|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    para = m.group(1) if m else next((p for p in text.split("\n\n") if p.strip() and not p.startswith("#")), "")
    para = " ".join(para.split())
    return para if len(para) <= limit else para[:limit].rsplit(" ", 1)[0] + "…"


def runs_of(name: str, runs_dir: Path = RUNS_DIR) -> list[dict]:
    """Các lượt đã lưu của dự án, mới nhất trước: {"run_id", "status"}."""
    out = []
    for p in sorted(runs_dir.glob("*.ui.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("project") == name:
            values = data.get("values") or {}
            out.append({"run_id": data.get("run_id") or p.name.split(".")[0], "module": values.get("module"),
                        "status": values.get("final_status") or "chưa xong"})
    return out


def threads_of(name: str, user: str, db_path: Path = DB_PATH) -> list[dict]:
    """Các cuộc chat của `user` thuộc dự án (gắn tag tên dự án), mới nhất trước: {"id", "name", "createdAt"}."""
    if not db_path.is_file():
        return []
    try:
        with sqlite3.connect(db_path) as con:
            rows = con.execute('SELECT "id", "name", "createdAt", "tags" FROM threads WHERE "userIdentifier" = ? '
                               'ORDER BY "createdAt" DESC', (user,)).fetchall()
    except sqlite3.Error:
        return []
    out = []
    for tid, tname, created, tags in rows:
        try:
            tags = json.loads(tags) if isinstance(tags, str) else (tags or [])
        except ValueError:
            tags = []
        if name in tags:
            module = next((t[len(MODULE_TAG):] for t in tags if isinstance(t, str) and t.startswith(MODULE_TAG)), None)
            out.append({"id": tid, "name": tname or "Cuộc chat", "createdAt": created or "", "module": module})
    return out


def modules_of(name: str, user: str, *, runs_dir: Path = RUNS_DIR, db_path: Path = DB_PATH,
               base: Path | None = None) -> list[dict]:
    """Các module của dự án: {"name", "title", "status", "run_id", "thread"} (thread: cuộc chat mới nhất của module)."""
    runs, chats = runs_of(name, runs_dir), threads_of(name, user, db_path)
    out = []
    for m in list_modules(name, base):
        last = next((r for r in runs if r.get("module") == m.name), None)
        chat = next((t for t in chats if t.get("module") == m.name), None)
        out.append({"name": m.name, "title": m.title, "status": last["status"] if last else None,
                    "run_id": last["run_id"] if last else None, "thread": chat["id"] if chat else None})
    return out


def overview(name: str, user: str, *, current_thread: str | None = None) -> str:
    """Nội dung tin chào của một dự án: mô tả, các module, các lượt đã chạy, các cuộc chat khác."""
    p = load_project(name)
    lines = [f"## {p.title}"]
    if desc := description(name):
        lines.append(desc)
    mods = modules_of(name, user)
    if mods:
        rows = []
        for m in mods:
            status = f"**{m['status']}** (`{m['run_id']}`)" if m["status"] else "chưa chạy"
            link = f"[{m['title']}](/thread/{m['thread']})" if m["thread"] and m["thread"] != current_thread \
                else m["title"]
            rows.append(f"| {link} | `modules/{m['name']}.md` | {status} |")
        lines.append("**Module** (mỗi module một cuộc chat, bấm tên để mở):\n\n| Module | File | Lượt gần nhất |\n"
                     "|---|---|---|\n" + "\n".join(rows))
    runs = runs_of(name)
    whole = [r for r in runs if not r.get("module")]
    if whole:
        last = whole[0]
        lines.append(f"**{len(whole)} lượt chạy cả dự án**, gần nhất `{last['run_id']}`: **{last['status']}**.")
    elif not runs:
        lines.append("Chưa chạy lượt nào.")
    chats = [t for t in threads_of(name, user) if t["id"] != current_thread and not t.get("module")]
    if chats:
        lines.append("**Các cuộc chat khác của dự án:**\n\n" + "\n".join(
            f"- [{t['name']}](/thread/{t['id']}) · {t['createdAt'][:10]}" for t in chats[:MAX_LISTED]))
        if len(chats) > MAX_LISTED:
            lines.append(f"_và {len(chats) - MAX_LISTED} cuộc chat cũ hơn ở thanh bên trái._")
    return "\n\n".join(lines)


def project_names() -> list[str]:
    return list_projects()
