"""Shared state của cả team (mục 5 trong spec)."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class TeamState(TypedDict, total=False):
    run_id: str
    # Dự án (projects/<tên>/): requirements, stack.md chèn vào prompt, lệnh test tự động
    project: str
    project_title: str
    requirements: str
    stack: str
    tests: dict               # {"command", "cwd", "timeout"} từ [tests] trong project.toml
    module: str               # chạy một module (projects/<tên>/modules/<module>.md) tiếp trên code đang có
    module_title: str

    # Model của lượt chạy (giao diện chọn); thiếu khóa thì đọc .env
    models: dict              # role -> "<provider>:<model>"
    escalate: dict            # role -> model vòng sửa cuối (chỉ ba, backend, frontend)

    # PM
    plan: list[dict]
    approved: bool
    review_notes: str
    review_round: int
    final_status: str

    # BA
    user_stories: list[dict]

    # Dev
    api_spec: str
    backend_code: list[str]   # đường dẫn file trong <output>/backend
    frontend_code: list[str]  # đường dẫn file trong <output>/frontend

    # Reviewer
    review_approved: bool
    review_findings: list[dict]  # mỗi finding có severity và owner: backend | frontend
    review_summary: str
    code_review_round: int    # số vòng review trong một vòng test, reset khi Tester trả bug

    # Tester
    test_cases: list[dict]
    test_report: str
    bugs: list[dict]          # mỗi bug có owner: backend | frontend
    iteration: int

    # Plane: map tên task logic -> id work item
    plane_tasks: dict

    # Nhật ký, reducer nối thêm (an toàn khi BE và FE chạy song song)
    log: Annotated[list[dict], operator.add]

    # Can thiệp của người dùng qua Quản lý trên giao diện (ui/manager.py), áp vào state giữa hai bước
    dismissed: dict                                   # mã finding/bug -> lý do bỏ qua
    manager_notes: Annotated[list[dict], operator.add]  # {"id", "role", "note", "at": số dòng log lúc thêm}
    interventions: Annotated[list[dict], operator.add]  # {"action", "text", "after"}: lệnh đã áp dụng


MAX_ROUNDS = 3
BLOCKING = ("critical", "required")


def blocking_findings(state, owner: str | None = None) -> list[dict]:
    """Finding chặn còn phải sửa; finding người dùng đã bỏ qua (dismissed) không tính."""
    return [f for f in state.get("review_findings", [])
            if f["severity"] in BLOCKING and not f.get("dismissed") and (owner is None or f["owner"] == owner)]


def open_bugs(state, owner: str | None = None) -> list[dict]:
    """Bug còn phải sửa; bug người dùng đã bỏ qua không tính."""
    return [b for b in state.get("bugs", []) if not b.get("dismissed") and (owner is None or b["owner"] == owner)]


def notes_for(state, role: str) -> list[dict]:
    """Ghi chú của người dùng cho `role` mà role đó chưa có lượt nào kể từ lúc thêm (mỗi ghi chú dùng một lần)."""
    log = state.get("log", [])
    def ran_since(at: int) -> bool:
        return any(e.get("node") == role or e.get("node", "").startswith(role + "_") for e in log[at:])
    return [n for n in state.get("manager_notes", []) if n["role"] == role and not ran_since(n["at"])]
