"""Provider: nơi gọi model cho từng role.

Ba tầng, từ chung tới riêng:
  adapter  (type)   cách nói chuyện với model: `anthropic`, `openai-compatible`, `claude-code`, `mock`
  provider (tên)    một endpoint cụ thể khai báo trong providers.toml: adapter + base_url + biến chứa key + tùy chọn
                    (providers.local.toml, không commit, thêm hoặc ghi đè provider cho riêng máy bạn)
  model theo role   chọn trong .env bằng "<provider>:<model>":
                      MODEL=claude-code:sonnet              mặc định cho mọi role
                      MODEL_BACKEND=opencode-go:glm-5.3     riêng một role (pm, ba, backend, frontend, reviewer, tester)
                    MODEL=mock: cả team chạy kịch bản giả, bỏ qua MODEL_<ROLE>.
                    MODEL_ALL (main.py đặt từ `--model`): một model cho cả team trong lần chạy đó, bỏ qua MODEL_<ROLE>.
  Tham số chung:    EFFORT[_<ROLE>], MAX_TOKENS[_<ROLE>]; thiếu thì lấy `effort`, `max_tokens` của provider.

Thêm một loại API mới: viết agents/providers/<adapter>.py có hàm call(target, role, prompt, schema) và đăng ký ở ADAPTERS.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILES = (ROOT / "providers.toml", ROOT / "providers.local.toml")
ROLES = ("pm", "ba", "backend", "frontend", "reviewer", "tester")
ADAPTER_TYPES = ("anthropic", "openai-compatible", "claude-code", "mock")


@dataclass(frozen=True)
class Provider:
    name: str
    type: str
    options: dict


@dataclass(frozen=True)
class Target:
    """Một role sẽ gọi model nào, qua provider nào, với tham số gì."""
    role: str
    provider: Provider
    model: str | None
    effort: str | None
    max_tokens: int | None

    @property
    def label(self) -> str:
        return self.provider.name if self.provider.type == "mock" else f"{self.provider.name}:{self.model}"


def load_providers(files: tuple[Path, ...] = CONFIG_FILES) -> dict[str, Provider]:
    merged: dict[str, dict] = {"mock": {"type": "mock"}}
    for f in files:
        if f.is_file():
            for name, cfg in (tomllib.loads(f.read_text(encoding="utf-8")).get("providers") or {}).items():
                merged[name] = {**merged.get(name, {}), **cfg}
    out = {}
    for name, cfg in merged.items():
        kind = cfg.get("type")
        if kind not in ADAPTER_TYPES:
            raise ValueError(f"Provider '{name}': type={kind!r} không hợp lệ (chọn {', '.join(ADAPTER_TYPES)})")
        out[name] = Provider(name, kind, {k: v for k, v in cfg.items() if k != "type"})
    return out


def parse_spec(spec: str) -> tuple[str, str | None]:
    """'provider:model' -> (provider, model). Chỉ tách ở dấu ':' đầu tiên, vì tên model có thể chứa ':'
    (ví dụ ollama:qwen3:8b). Không có ':' thì model lấy từ default_model của provider."""
    name, _, model = spec.strip().partition(":")
    return name.strip(), (model.strip() or None)


def _env_role(key: str, role: str) -> str | None:
    return os.getenv(f"{key}_{role.upper()}") or os.getenv(key) or None


def target_for(role: str, providers: dict[str, Provider] | None = None) -> Target:
    providers = providers if providers is not None else load_providers()
    forced = os.getenv("MODEL_ALL")
    default = forced or os.getenv("MODEL") or "mock"
    name, model = parse_spec(default)
    if name not in providers:  # kiểm tra cả khi mọi role đều có MODEL_<ROLE>
        src = "--model" if forced else "MODEL"
        raise ValueError(f"{src}: provider '{name}' chưa khai báo trong providers.toml "
                         f"(có: {', '.join(sorted(providers))})")
    if not forced and name != "mock" and (override := os.getenv(f"MODEL_{role.upper()}")):
        name, model = parse_spec(override)
    if name not in providers:
        raise ValueError(f"{role}: provider '{name}' chưa khai báo trong providers.toml "
                         f"(có: {', '.join(sorted(providers))})")
    p = providers[name]
    model = model or p.options.get("default_model")
    if p.type != "mock" and not model:
        raise ValueError(f"{role}: thiếu model cho provider '{name}': dùng '{name}:<model>' "
                         f"hoặc đặt default_model trong providers.toml")
    effort = _env_role("EFFORT", role) or p.options.get("effort")
    max_tokens = _env_role("MAX_TOKENS", role) or p.options.get("max_tokens")
    return Target(role, p, model, effort, int(max_tokens) if max_tokens else None)


def missing_keys(providers: dict[str, Provider] | None = None) -> list[str]:
    """Role nào dùng provider có `api_key_env` mà biến đó chưa có giá trị; kiểm tra trước khi chạy."""
    providers = providers if providers is not None else load_providers()
    out = []
    for role in ROLES:
        try:
            p = target_for(role, providers).provider
        except ValueError:
            continue  # lỗi cấu hình đã được describe() báo
        env = p.options.get("api_key_env")
        if env and not os.getenv(env):
            out.append(f"{role}: provider '{p.name}' cần {env} trong .env")
    return out


def uses_real_model(providers: dict[str, Provider] | None = None) -> bool:
    providers = providers if providers is not None else load_providers()
    return any(target_for(r, providers).provider.type != "mock" for r in ROLES)


def describe(providers: dict[str, Provider] | None = None) -> str:
    """Một dòng tóm tắt role nào chạy bằng gì, in ra đầu mỗi lần chạy."""
    providers = providers if providers is not None else load_providers()
    parts = []
    for role in ROLES:
        try:
            parts.append(f"{role}={target_for(role, providers).label}")
        except ValueError as e:
            parts.append(f"{role}=LỖI({e})")
    return " · ".join(parts)


def adapter(kind: str) -> Callable:
    # import khi cần để thiếu thư viện của một adapter không làm hỏng adapter khác
    if kind == "anthropic":
        from agents.providers import anthropic_api as mod
    elif kind == "openai-compatible":
        from agents.providers import openai_compat as mod
    elif kind == "claude-code":
        from agents.providers import claude_code as mod
    else:
        raise ValueError(f"Adapter {kind!r} không gọi model (mock được xử lý ở agents/common.py)")
    return mod.call
