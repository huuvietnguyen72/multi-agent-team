"""Phần dùng chung: gọi model cho một role (theo cấu hình trong agents/providers), dựng prompt từ state."""
from __future__ import annotations

import json
import time

from agents import mock
from agents.escalation import pick_target
from agents.providers import ROLES, adapter, describe
from tools.runlog import set_call_info

__all__ = ["ROLES", "ask", "describe_providers", "dump", "with_project_context"]


def describe_providers() -> str:
    return describe()


def with_project_context(state, prompt: str) -> str:
    """Chèn stack và quy ước kỹ thuật của dự án (projects/<tên>/stack.md) vào đầu prompt.
    Skill của role giữ nguyên tắc chung; phần cụ thể của từng dự án nằm ở đây."""
    stack = (state.get("stack") or "").strip()
    if not stack:
        return prompt
    title = state.get("project_title") or "dự án"
    return f"# Stack và quy ước kỹ thuật của {title}\n\n{stack}\n\n---\n\n{prompt}"


def ask(role: str, node: str, state, prompt: str, schema):
    """Gọi model đã chọn cho `role`: state["models"] (chọn trên giao diện) hoặc MODEL / MODEL_<ROLE> trong .env,
    đổi sang model vòng cuối nếu đây là lần sửa cuối. Provider mock thì dùng agents/mock.py.
    Model và thời gian gọi được ghi vào dòng log kế tiếp của node."""
    target, before = pick_target(role, state)
    if before:
        print(f"   ↑ {role}: đổi từ {before} sang {target.label} vì đây là vòng sửa cuối")
    start = time.monotonic()
    try:
        if target.provider.type == "mock":
            return getattr(mock, node)(state)
        return adapter(target.provider.type)(target, role, with_project_context(state, prompt), schema)
    finally:
        info = {"model": target.label, "seconds": round(time.monotonic() - start, 1)}
        if before:
            info["escalated_from"] = before
        set_call_info(info)


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
