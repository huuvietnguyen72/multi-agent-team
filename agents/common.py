"""Phần dùng chung: gọi model cho một role (theo cấu hình trong agents/providers), dựng prompt từ state."""
from __future__ import annotations

import json
import time

from agents import mock
from agents.escalation import pick_target
from agents.providers import ROLES, adapter, describe
from state import notes_for
from tools.runlog import progress, set_call_info

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


def with_user_input(state, role: str, prompt: str) -> str:
    """Thêm ghi chú người dùng dặn riêng role này và các mục người dùng đã bỏ qua (qua Quản lý trên giao diện)."""
    extra = []
    if notes := notes_for(state, role):
        extra.append("Người dùng dặn riêng cho lượt này (làm theo, trừ khi trái requirements):\n"
                     + "\n".join(f"- {n['note']}" for n in notes))
    if dismissed := state.get("dismissed"):
        extra.append("Người dùng đã bỏ qua các finding/bug sau, không sửa và không nêu lại:\n"
                     + "\n".join(f"- {k}: {why}" for k, why in dismissed.items()))
    return prompt + "".join(f"\n\n{e}" for e in extra)


def ask(role: str, node: str, state, prompt: str, schema):
    """Gọi model đã chọn cho `role`: state["models"] (chọn trên giao diện) hoặc MODEL / MODEL_<ROLE> trong .env,
    đổi sang model vòng cuối nếu đây là lần sửa cuối. Provider mock thì dùng agents/mock.py.
    Model và thời gian gọi được ghi vào dòng log kế tiếp của node."""
    target, before = pick_target(role, state)
    if before:
        print(f"   ↑ {role}: đổi từ {before} sang {target.label} vì đây là vòng sửa cuối")
    progress("model", model=target.label, **({"escalated_from": before} if before else {}))
    start = time.monotonic()
    try:
        if target.provider.type == "mock":
            return getattr(mock, node)(state)
        return adapter(target.provider.type)(target, role, with_project_context(state, with_user_input(state, role, prompt)),
                                             schema)
    finally:
        info = {"model": target.label, "seconds": round(time.monotonic() - start, 1)}
        if before:
            info["escalated_from"] = before
        set_call_info(info)


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
