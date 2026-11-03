"""Phần dùng chung: chọn agent giả hay LLM, dựng prompt từ state."""
from __future__ import annotations

import json
import os

from agents import claude_code, llm, mock

MODES = ("mock", "llm", "claude-code")


def mode() -> str:
    return os.getenv("AGENT_MODE", "mock")


def ask(role: str, node: str, state, prompt: str, schema):
    """mock: hàm cố định trong agents/mock.py; llm: gọi Claude API bằng API key;
    claude-code: gọi `claude -p`, dùng gói thuê bao Claude (Pro/Max) đang đăng nhập."""
    m = mode()
    if m == "mock":
        return getattr(mock, node)(state)
    if m == "claude-code":
        return claude_code.call_structured(role, prompt, schema)
    if m == "llm":
        return llm.call_structured(role, prompt, schema)
    raise ValueError(f"AGENT_MODE không hợp lệ: {m!r} (chọn một trong {', '.join(MODES)})")


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
