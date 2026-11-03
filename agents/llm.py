"""Gọi Claude với skills của từng role làm system prompt, ép đầu ra theo schema Pydantic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

SKILLS = Path(__file__).resolve().parent.parent / "skills"
T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # đọc ANTHROPIC_API_KEY từ môi trường / .env
    return _client


def load_skill(role: str) -> str:
    """Đọc skills/<role>/SKILL.md, bỏ frontmatter (name, description) trước khi làm system prompt."""
    text = (SKILLS / role / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.lstrip()


def model_for(role: str) -> str:
    # Cho phép đặt model riêng từng role, ví dụ MODEL_TESTER=claude-sonnet-5-5
    return os.getenv(f"MODEL_{role.upper()}") or os.getenv("LLM_MODEL", "claude-opus-5-5")


def call_structured(role: str, prompt: str, schema: type[T]) -> T:
    """Một lần gọi LLM, thử lại 1 lần nếu đầu ra sai schema (mục 10 trong spec)."""
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            # Stream để không bị timeout khi Dev sinh nhiều file code.
            with client().beta.messages.stream(
                model=model_for(role),
                max_tokens=64000,
                # Skill không đổi giữa các lượt gọi nên được cache, giảm chi phí các vòng lặp sau.
                system=[{"type": "text", "text": load_skill(role), "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": os.getenv("LLM_EFFORT", "medium")},
                # Nếu bị bộ lọc an toàn từ chối, API tự chạy lại trên model dự phòng.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                msg = stream.get_final_message()
            if msg.stop_reason == "refusal":
                raise RuntimeError(f"{role}: model từ chối yêu cầu ({msg.stop_details})")
            if msg.stop_reason == "max_tokens":
                raise RuntimeError(f"{role}: đầu ra bị cắt do max_tokens")
            parsed = msg.parsed_output
            if parsed is None:
                text = "".join(b.text for b in msg.content if b.type == "text")
                parsed = schema.model_validate_json(text)
            return parsed
        except (ValidationError, ValueError) as e:
            last_err = e
            print(f"   [llm] {role}: đầu ra sai schema, thử lại ({attempt + 1}/2)")
    raise RuntimeError(f"{role}: LLM trả sai định dạng 2 lần: {last_err}")
