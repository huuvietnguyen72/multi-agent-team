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


MAX_ROUNDS = 3
BLOCKING = ("critical", "required")


def blocking_findings(state, owner: str | None = None) -> list[dict]:
    return [f for f in state.get("review_findings", [])
            if f["severity"] in BLOCKING and (owner is None or f["owner"] == owner)]
