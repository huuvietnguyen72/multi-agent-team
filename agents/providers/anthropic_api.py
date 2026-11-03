"""Adapter `anthropic`: Claude API qua thư viện `anthropic`, hoặc endpoint tương thích Anthropic Messages API.

Tùy chọn trong providers.toml:
  api_key_env      tên biến chứa key (mặc định: để SDK tự tìm ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ant auth login)
  base_url         endpoint khác Claude API (gateway tương thích Anthropic); bỏ trống = Claude API
  server_fallback  true: bật fallback phía server khi bị bộ lọc an toàn từ chối (chỉ Claude API hỗ trợ)
  prompt_cache     true (mặc định): cache system prompt (skill) giữa các lượt gọi
  effort, max_tokens, default_model
"""
from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from agents.providers.base import api_key, with_schema_retry
from agents.skills import load_skill

T = TypeVar("T", bound=BaseModel)

_clients: dict[tuple, anthropic.Anthropic] = {}


def _client(target) -> anthropic.Anthropic:
    opts = target.provider.options
    key = api_key(target, required=False)
    cache_key = (opts.get("base_url"), key)
    if cache_key not in _clients:
        kwargs = {}
        if key:
            kwargs["api_key"] = key
        if opts.get("base_url"):
            kwargs["base_url"] = opts["base_url"]
        _clients[cache_key] = anthropic.Anthropic(**kwargs)
    return _clients[cache_key]


def call(target, role: str, prompt: str, schema: type[T]) -> T:
    opts = target.provider.options
    system = {"type": "text", "text": load_skill(role)}
    if opts.get("prompt_cache", True):
        system["cache_control"] = {"type": "ephemeral"}  # skill không đổi giữa các lượt gọi
    kwargs = dict(model=target.model, max_tokens=target.max_tokens or 64000, system=[system],
                  messages=[{"role": "user", "content": prompt}], output_format=schema)
    if target.effort:
        kwargs["output_config"] = {"effort": target.effort}
    if opts.get("server_fallback"):
        kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

    def attempt() -> T:
        # Stream để không bị timeout khi Dev sinh nhiều file code.
        with _client(target).beta.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise RuntimeError(f"{role} ({target.label}): model từ chối yêu cầu ({msg.stop_details})")
        if msg.stop_reason == "max_tokens":
            raise RuntimeError(f"{role} ({target.label}): đầu ra bị cắt do max_tokens={kwargs['max_tokens']}")
        if msg.parsed_output is not None:
            return msg.parsed_output
        return schema.model_validate_json("".join(b.text for b in msg.content if b.type == "text"))

    return with_schema_retry(target, schema, attempt)
