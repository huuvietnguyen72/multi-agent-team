"""Adapter `claude-code`: gọi Claude qua Claude Code CLI (`claude -p`), dùng gói thuê bao đang đăng nhập (Pro/Max).

Yêu cầu: đã cài Claude Code và đăng nhập bằng tài khoản claude.ai (chạy `claude` một lần, gõ /login).
Mỗi lần gọi là một tiến trình `claude -p` độc lập: system prompt = skills/<role>/SKILL.md, không có tool, không MCP,
không đọc settings/hook của máy, đầu ra ép theo JSON Schema sinh từ model Pydantic (--json-schema).
Lượt dùng tính vào hạn mức của gói thuê bao, dùng chung với lúc bạn chat trong Claude Code.

Tùy chọn trong providers.toml:
  command          lệnh chạy Claude Code (mặc định "claude")
  timeout          giây tối đa mỗi lần gọi (mặc định 1800)
  strip_api_keys   true (mặc định): bỏ ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN khỏi tiến trình con để luôn dùng gói thuê bao
  effort, default_model  (model: alias như sonnet/opus hoặc tên đầy đủ)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import TypeVar

from pydantic import BaseModel

from agents.providers.base import with_schema_retry
from agents.skills import skill_path

T = TypeVar("T", bound=BaseModel)

_API_AUTH_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _exe(target) -> str:
    name = target.provider.options.get("command", "claude")
    exe = shutil.which(name)
    if not exe:
        raise RuntimeError(f"Không tìm thấy lệnh `{name}` trên PATH. Cài Claude Code rồi đăng nhập bằng /login.")
    return exe


def _env(target) -> dict:
    env = dict(os.environ)
    if target.provider.options.get("strip_api_keys", True):
        for k in _API_AUTH_VARS:
            env.pop(k, None)  # bắt buộc dùng đăng nhập thuê bao, kể cả khi .env có key (hoặc key rỗng)
    return env


def _command(target, role: str, schema: type[BaseModel]) -> list[str]:
    cmd = [
        _exe(target), "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema.model_json_schema()),
        "--system-prompt-file", str(skill_path(role)),
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--no-session-persistence",
        "--model", target.model,
    ]
    if target.effort:
        cmd += ["--effort", target.effort]
    return cmd


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


def call(target, role: str, prompt: str, schema: type[T]) -> T:
    timeout = int(target.provider.options.get("timeout", 1800))

    def attempt() -> T:
        try:
            proc = subprocess.run(
                _command(target, role, schema), input=prompt, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, env=_env(target),
                cwd=tempfile.gettempdir(),  # tránh nạp CLAUDE.md hay settings của thư mục dự án
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"{role}: claude -p chạy quá {timeout}s (tăng `timeout` của provider)") from e
        if not proc.stdout.strip():
            raise RuntimeError(f"{role}: claude -p thoát mã {proc.returncode}: {proc.stderr.strip()[:500]}")
        return _parse(role, proc.stdout, schema)

    return with_schema_retry(target, schema, attempt)
