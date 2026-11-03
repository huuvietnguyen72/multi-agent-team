"""Phần dùng chung của các adapter: lấy API key, tách JSON khỏi câu trả lời, thử lại khi sai schema."""
from __future__ import annotations

import os
import re
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def api_key(target, required: bool = True) -> str | None:
    """Key đọc từ biến môi trường có tên ở `api_key_env` của provider (không bao giờ ghi key vào providers.toml)."""
    env = target.provider.options.get("api_key_env")
    key = os.getenv(env) if env else None
    if required and not key:
        where = f"biến {env} trong .env" if env else "api_key_env trong providers.toml"
        raise RuntimeError(f"{target.role}: provider '{target.provider.name}' cần API key ({where})")
    return key


def extract_json(text: str) -> str:
    """Bỏ khối ```json ... ``` hoặc chữ thừa quanh object nếu model vẫn thêm vào."""
    text = text.strip()
    if (m := re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S)):
        text = m.group(1)
    if not text.startswith("{") and "{" in text:
        text = text[text.find("{"):text.rfind("}") + 1]
    return text


def with_schema_retry(target, schema: type[T], attempt: Callable[[], T]) -> T:
    """Chạy `attempt` (một lần gọi model + parse); sai schema thì thử lại đúng 1 lần."""
    last: Exception | None = None
    for i in range(2):
        try:
            return attempt()
        except (ValidationError, ValueError) as e:
            last = e
            print(f"   [{target.label}] {target.role}: đầu ra sai schema, thử lại ({i + 1}/2)")
    raise RuntimeError(f"{target.role} ({target.label}): trả sai định dạng 2 lần: {last}")
