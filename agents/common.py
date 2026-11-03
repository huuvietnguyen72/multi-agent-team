"""Phần dùng chung: gọi model cho một role (theo cấu hình trong agents/providers), dựng prompt từ state."""
from __future__ import annotations

import json

from agents import mock
from agents.providers import ROLES, adapter, describe, target_for

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
    """Gọi model đã chọn cho `role` (MODEL / MODEL_<ROLE> trong .env); provider mock thì dùng agents/mock.py."""
    target = target_for(role)
    if target.provider.type == "mock":
        return getattr(mock, node)(state)
    return adapter(target.provider.type)(target, role, with_project_context(state, prompt), schema)


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
