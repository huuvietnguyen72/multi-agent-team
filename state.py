"""Shared state của cả team (mục 5 trong spec)."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class TeamState(TypedDict, total=False):
    run_id: str
    requirements: str

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
    backend_code: list[str]   # đường dẫn file trong output/backend
    frontend_code: list[str]  # đường dẫn file trong output/frontend

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
