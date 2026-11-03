"""Gọi Claude qua Claude Code CLI (`claude -p`), dùng gói thuê bao đang đăng nhập (Pro/Max) thay vì API key.

Yêu cầu: đã cài Claude Code và đăng nhập bằng tài khoản claude.ai (chạy `claude` một lần, gõ /login).
Mỗi lần gọi là một tiến trình `claude -p` độc lập:
  - system prompt = skills/<role>/SKILL.md
  - không có tool nào (--tools ""), không MCP, không đọc settings/hook của máy
  - ép đầu ra theo JSON Schema sinh từ model Pydantic (--json-schema)
Lượt dùng tính vào hạn mức của gói thuê bao, dùng chung với lúc bạn chat trong Claude Code.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agents.llm import SKILLS

T = TypeVar("T", bound=BaseModel)

# Biến môi trường làm Claude Code chuyển sang tính tiền API thay vì dùng gói thuê bao
_API_AUTH_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def model_for(role: str) -> str:
    # Mặc định "sonnet" để tiết kiệm hạn mức gói Pro; đặt CC_MODEL=opus hoặc CC_MODEL_<ROLE> nếu muốn
    return os.getenv(f"CC_MODEL_{role.upper()}") or os.getenv("CC_MODEL", "sonnet")


def _claude_exe() -> str:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("Không tìm thấy lệnh `claude` trên PATH. Cài Claude Code rồi đăng nhập bằng /login.")
    return exe


def _env() -> dict:
    env = dict(os.environ)
    for k in _API_AUTH_VARS:
        env.pop(k, None)  # bắt buộc dùng đăng nhập thuê bao, kể cả khi .env có key (hoặc key rỗng)
    return env


def _command(role: str, schema: type[BaseModel]) -> list[str]:
    return [
        _claude_exe(), "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema.model_json_schema()),
        "--system-prompt-file", str(SKILLS / role / "SKILL.md"),
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--no-session-persistence",
        "--model", model_for(role),
        "--effort", os.getenv("LLM_EFFORT", "medium"),
    ]


def _parse(role: str, stdout: str, schema: type[T]) -> T:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"{role}: claude -p không trả JSON: {stdout[:500]}") from e
    if data.get("is_error") or data.get("subtype") != "success":
        raise RuntimeError(f"{role}: claude -p lỗi ({data.get('subtype')}, "
                           f"api_error_status={data.get('api_error_status')}): {str(data.get('result'))[:500]}")
    if data.get("stop_reason") == "refusal":
        raise RuntimeError(f"{role}: model từ chối yêu cầu")
    if data.get("structured_output") is not None:
        return schema.model_validate(data["structured_output"])
    return schema.model_validate_json(data.get("result") or "")


def call_structured(role: str, prompt: str, schema: type[T]) -> T:
    """Một lần gọi `claude -p`, thử lại 1 lần nếu đầu ra sai schema (cùng luật với agents/llm.py)."""
    timeout = int(os.getenv("CC_TIMEOUT", "1800"))
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            proc = subprocess.run(
                _command(role, schema), input=prompt, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, env=_env(),
                cwd=tempfile.gettempdir(),  # tránh nạp CLAUDE.md hay settings của thư mục dự án
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"{role}: claude -p chạy quá {timeout}s (đặt CC_TIMEOUT để tăng)") from e
        if not proc.stdout.strip():
            raise RuntimeError(f"{role}: claude -p thoát mã {proc.returncode}: {proc.stderr.strip()[:500]}")
        try:
            return _parse(role, proc.stdout, schema)
        except (ValidationError, ValueError) as e:
            last_err = e
            print(f"   [claude-code] {role}: đầu ra sai schema, thử lại ({attempt + 1}/2)")
    raise RuntimeError(f"{role}: claude -p trả sai định dạng 2 lần: {last_err}")
