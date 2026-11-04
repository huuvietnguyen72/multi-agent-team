"""Adapter `openai-compatible`: mọi endpoint theo chuẩn OpenAI Chat Completions
(OpenCode Go/Zen, OpenAI, OpenRouter, DeepSeek, Gemini, Groq, Ollama, LM Studio, vLLM, ...).

Tùy chọn trong providers.toml:
  base_url          bắt buộc, phần trước /chat/completions, ví dụ https://api.openai.com/v1
  api_key_env       tên biến chứa key; bỏ trống cho server chạy local không cần key
  response_format   "json_schema" (mặc định) | "json_object" | "none": cách ép JSON, tùy server hỗ trợ
  effort_param      tên tham số effort gửi đi (mặc định "reasoning_effort"); chỉ gửi khi có EFFORT
  max_tokens_param  tên tham số trần token (mặc định "max_tokens"; OpenAI mới dùng "max_completion_tokens")
  session_header    tên header chứa mã phiên ổn định cho mỗi cuộc hội thoại (OpenCode Go: "x-opencode-session")
  user_agent        mặc định "multi-agent-team/0.1"
  headers           bảng header thêm, ví dụ { "HTTP-Referer" = "..." }
  read_timeout      giây tối đa giữa hai chunk stream (mặc định 300)
  effort, max_tokens (mặc định 64000, tính cả token suy luận), default_model
Schema JSON luôn được ghi thêm trong system prompt để model nào ép lỏng vẫn trả đúng định dạng.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import TypeVar

import requests
from pydantic import BaseModel

from agents.providers.base import api_key, extract_json, with_schema_retry
from agents.skills import load_skill
from tools.runlog import progress

T = TypeVar("T", bound=BaseModel)

USER_AGENT = "multi-agent-team/0.1"


def _messages(role: str, prompt: str, schema: type[BaseModel]) -> list[dict]:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    system = (f"{load_skill(role)}\n\n---\n\nĐịnh dạng trả lời: chỉ một object JSON hợp lệ theo JSON Schema dưới đây, "
              f"không kèm giải thích, không bọc trong ```.\n{schema_json}")
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


def _body(target, role: str, prompt: str, schema: type[BaseModel]) -> dict:
    opts = target.provider.options
    body = {"model": target.model, "messages": _messages(role, prompt, schema), "stream": True,
            opts.get("max_tokens_param", "max_tokens"): target.max_tokens or 64000}
    mode = opts.get("response_format", "json_schema")
    if mode == "json_schema":
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "schema": schema.model_json_schema(), "strict": False}}
    elif mode == "json_object":
        body["response_format"] = {"type": "json_object"}
    elif mode != "none":
        raise ValueError(f"Provider '{target.provider.name}': response_format={mode!r} không hợp lệ")
    if target.effort:
        body[opts.get("effort_param", "reasoning_effort")] = target.effort
    return body


def _headers(target, session: str) -> dict:
    opts = target.provider.options
    headers = {"Content-Type": "application/json", "User-Agent": opts.get("user_agent", USER_AGENT)}
    if (key := api_key(target, required=bool(opts.get("api_key_env")))):
        headers["Authorization"] = f"Bearer {key}"
    if opts.get("session_header"):
        headers[opts["session_header"]] = session
    headers.update(opts.get("headers") or {})
    return headers


def _stream(target, body: dict, headers: dict) -> tuple[str, str | None, int]:
    """Gửi request stream (SSE), ghép phần content; reasoning chỉ đếm độ dài để chẩn đoán.
    Trả (content, finish_reason, số ký tự suy luận)."""
    opts = target.provider.options
    base = opts.get("base_url")
    if not base:
        raise RuntimeError(f"Provider '{target.provider.name}': thiếu base_url trong providers.toml")
    with requests.post(f"{base.rstrip('/')}/chat/completions", headers=headers, json=body, stream=True,
                       timeout=(15, int(opts.get("read_timeout", 300)))) as r:
        if r.status_code >= 400:
            hint = " (hết hạn mức hoặc bị giới hạn tốc độ?)" if r.status_code == 429 else ""
            raise RuntimeError(f"{target.role} ({target.label}): HTTP {r.status_code}{hint}: {r.text[:500]}")
        parts, finish, reasoning = [], None, 0
        chars, last_report = 0, time.monotonic()
        for line in r.iter_lines():
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("error"):
                raise RuntimeError(f"{target.role} ({target.label}): lỗi giữa stream: {chunk['error']}")
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if (text := delta.get("content")):
                    parts.append(text)
                    chars += len(text)
                reasoning += len(delta.get("reasoning_content") or delta.get("reasoning") or "")
                finish = choice.get("finish_reason") or finish
            if time.monotonic() - last_report >= 2:  # báo giao diện số ký tự đã nhận, tối đa 2 giây một lần
                progress("stream", chars=chars)
                last_report = time.monotonic()
    return "".join(parts), finish, reasoning


def call(target, role: str, prompt: str, schema: type[T]) -> T:
    body = _body(target, role, prompt, schema)
    headers = _headers(target, f"multi-agent-team-{role}-{uuid.uuid4().hex[:12]}")  # cùng phiên khi thử lại

    def attempt() -> T:
        content, finish, reasoning = _stream(target, body, headers)
        if finish == "length":
            raise RuntimeError(
                f"{role} ({target.label}): đầu ra bị cắt do max_tokens={target.max_tokens or 64000} "
                f"(đã nhận {len(content):,} ký tự trả lời, {reasoning:,} ký tự suy luận). "
                f"Tăng MAX_TOKENS_{role.upper()} hoặc giảm EFFORT_{role.upper()}")
        return schema.model_validate_json(extract_json(content))

    return with_schema_retry(target, schema, attempt)
