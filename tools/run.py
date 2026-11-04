"""Chuẩn bị một lượt chạy: nạp dự án, kiểm tra model và API key theo role, dựng state ban đầu.
main.py và giao diện (ui/app.py) cùng gọi prepare_run() nên kiểm tra giống hệt nhau."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agents.providers import ESCALATABLE, ROLES, check_models, default_specs, escalation_specs, load_providers, \
    target_for
from tools.project import Project, load_project


@dataclass(frozen=True)
class RunSetup:
    project: Project
    run_id: str
    state: dict               # state ban đầu cho graph
    config: dict              # {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
    models: dict[str, str]    # role -> label sẽ dùng (role cấu hình sai thì không có)
    escalate: dict[str, str]  # role -> label vòng sửa cuối, chỉ role có khai báo
    problems: list[str]       # rỗng là chạy được
    real_model: bool          # có lần gọi nào tới model thật không


def _labels(specs: dict[str, str], providers) -> dict[str, str]:
    out = {}
    for role, spec in specs.items():
        try:
            out[role] = target_for(role, providers, spec=spec).label
        except ValueError:
            pass
    return out


def prepare_run(project: str, requirements: str | None = None, *,
                models: dict[str, str] | None = None, escalate: dict[str, str] | None = None,
                mock: bool = False, run_id: str | None = None, output_dir: Path | None = None) -> RunSetup:
    """FileNotFoundError khi không có dự án. Lỗi cấu hình model không ném ra mà nằm trong `problems`."""
    proj = load_project(project, requirements)
    out_dir = Path(output_dir) if output_dir is not None else proj.output_dir
    os.environ["OUTPUT_DIR"] = str(out_dir)  # tools/file_tools.py ghi vào đây
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    if mock:
        models, escalate = {r: "mock" for r in ROLES}, {}
    models = dict(models) if models is not None else None
    escalate = dict(escalate) if escalate is not None else None

    problems: list[str] = []
    try:
        providers = load_providers()
    except ValueError as e:  # providers.toml sai cú pháp hoặc type không hợp lệ
        providers = None
        problems.append(str(e))
    esc_specs = escalate
    if providers is not None:
        problems += check_models(models, escalate, providers)
        if esc_specs is None:
            try:
                esc_specs = escalation_specs()
            except ValueError:
                esc_specs = {}  # đã có trong problems
        used = _labels(models, providers) if models is not None else default_specs(providers)
        if models is not None:  # role không có trong `models` thì đọc .env
            used = {**{r: v for r, v in default_specs(providers).items() if r not in models}, **used}
        last = _labels({r: s for r, s in esc_specs.items() if r in ESCALATABLE}, providers)
    else:
        used, last = {}, {}
    used = {r: used[r] for r in ROLES if r in used}

    state = {
        "run_id": run_id, "project": proj.name, "project_title": proj.title,
        "requirements": proj.requirements, "stack": proj.stack,
        "tests": {"command": proj.test_command, "cwd": proj.test_cwd, "timeout": proj.test_timeout},
        "log": [],
    }
    if models is not None:
        state["models"] = dict(models)
    if escalate is not None:
        state["escalate"] = dict(escalate)
    real = any(v != "mock" for v in used.values()) or \
        any(v != "mock" and used.get(r) != "mock" for r, v in last.items())
    return RunSetup(project=proj, run_id=run_id, state=state,
                    config={"configurable": {"thread_id": run_id}, "recursion_limit": 50},
                    models=used, escalate=last, problems=problems, real_model=real)


HISTORY_KEEP = 5  # số bản đầu ra cũ giữ lại trong output_history/


OUTPUT_MARK = ".output_run"  # nằm cạnh output/: lượt nào đã ghi output/ hiện tại


def output_run_id(out_dir: Path) -> str | None:
    """Mã lượt đã tạo thư mục output/ hiện tại (ghi bởi archive_output), None nếu chưa biết."""
    mark = Path(out_dir).parent / OUTPUT_MARK
    try:
        return mark.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def archive_output(out_dir: Path, run_id: str) -> Path | None:
    """Chuyển đầu ra của lượt trước sang <dự án>/output_history/<mã lượt trước>/ để lượt `run_id` bắt đầu từ thư
    mục trống: file cũ không lẫn vào kết quả mới, và phần sửa (diff) của "bản đầu" so với rỗng chứ không so với
    lượt trước. Giữ HISTORY_KEEP bản gần nhất. Trả về thư mục đã chuyển tới, None nếu không có gì để chuyển."""
    out_dir = Path(out_dir)
    previous = output_run_id(out_dir) or f"truoc-{run_id}"
    moved = None
    if out_dir.is_dir() and any(out_dir.iterdir()):
        history = out_dir.parent / "output_history"
        history.mkdir(parents=True, exist_ok=True)
        dest = history / previous
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        out_dir.rename(dest)
        for old in sorted(p for p in history.iterdir() if p.is_dir())[:-HISTORY_KEEP]:
            shutil.rmtree(old, ignore_errors=True)
        moved = dest
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / OUTPUT_MARK).write_text(run_id, encoding="utf-8")
    return moved


def format_models(setup: RunSetup, code: bool = False) -> str:
    """'pm=claude-code:sonnet · ... · backend=opencode-go:glm-5.3 (vòng cuối: claude-code:opus) · ...';
    mọi role cùng một model và không có vòng cuối thì chỉ 'cả team=<model>'."""
    q0 = (lambda m: f"`{m}`") if code else (lambda m: m)
    values = set(setup.models.values())
    if len(values) == 1 and len(setup.models) == len(ROLES) and not setup.escalate:
        return f"cả team={q0(values.pop())}"
    parts = []
    for role in ROLES:
        model = setup.models.get(role, "LỖI")
        q = (lambda m: f"`{m}`") if code else (lambda m: m)  # markdown đọc ":tên" là directive, nên bọc code
        label = q(model)
        if role in setup.escalate and setup.escalate[role] != model and model != "mock":
            label += f" (vòng cuối: {q(setup.escalate[role])})"
        parts.append(f"{role}={label}")
    return " · ".join(parts)
