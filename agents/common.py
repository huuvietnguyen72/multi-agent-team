"""Phần dùng chung: chọn agent giả hay LLM, dựng prompt từ state."""
from __future__ import annotations

import json
import os

from agents import mock
from agents.llm import call_structured


def mode() -> str:
    return os.getenv("AGENT_MODE", "mock")


def ask(role: str, node: str, state, prompt: str, schema):
    """mock: dùng hàm cố định trong agents/mock.py; llm: gọi Claude với skills của role."""
    if mode() == "mock":
        return getattr(mock, node)(state)
    return call_structured(role, prompt, schema)


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
