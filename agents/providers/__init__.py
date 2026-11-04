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
ESCALATABLE: tuple[str, ...] = ("ba", "backend", "frontend")  # role được tự nâng model ở vòng sửa cuối


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


def target_for(role: str, providers: dict[str, Provider] | None = None, spec: str | None = None) -> Target:
    """Model của `role`. `spec` ("<provider>:<model>", ví dụ chọn trên giao diện) thắng MODEL_ALL, MODEL
    và MODEL_<ROLE>; EFFORT_<ROLE>, MAX_TOKENS_<ROLE> và default_model vẫn áp dụng như thường."""
    providers = providers if providers is not None else load_providers()
    if spec:
        name, model = parse_spec(spec)
    else:
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


def default_specs(providers: dict[str, Provider] | None = None) -> dict[str, str]:
    """Role -> model đang chọn trong .env (dạng label). Role cấu hình sai thì bỏ qua."""
    providers = providers if providers is not None else load_providers()
    out = {}
    for role in ROLES:
        try:
            out[role] = target_for(role, providers).label
        except ValueError:
            pass
    return out


def escalation_specs() -> dict[str, str]:
    """Model vòng sửa cuối: ESCALATE_<ROLE> thắng ESCALATE, chỉ cho các role trong ESCALATABLE."""
    for role in ROLES:
        if role not in ESCALATABLE and os.getenv(f"ESCALATE_{role.upper()}"):
            raise ValueError(f"ESCALATE_{role.upper()}: chỉ dùng được cho {', '.join(ESCALATABLE)}")
    out = {}
    for role in ESCALATABLE:
        spec = (os.getenv(f"ESCALATE_{role.upper()}") or os.getenv("ESCALATE") or "").strip()
        if spec:
            out[role] = spec
    return out


def model_choices(providers: dict[str, Provider] | None = None) -> list[str]:
    """Danh sách cho ô chọn model: mock, mỗi provider với default_model, cùng mọi model đang khai báo
    trong MODEL, MODEL_<ROLE>, ESCALATE* và UI_MODELS (phân cách bằng dấu phẩy)."""
    providers = providers if providers is not None else load_providers()
    found = {"mock"}
    for p in providers.values():
        if p.type != "mock" and p.options.get("default_model"):
            found.add(f"{p.name}:{p.options['default_model']}")
    keys = ["MODEL", "ESCALATE"] + [f"{k}_{r.upper()}" for k in ("MODEL", "ESCALATE") for r in ROLES]
    raw = [os.getenv(k) or "" for k in keys] + (os.getenv("UI_MODELS") or "").split(",")
    found.update(v.strip() for v in raw if v.strip())
    return sorted(found)


def _key_problem(target: Target) -> str | None:
    env = target.provider.options.get("api_key_env")
    if env and not os.getenv(env):
        return f"provider '{target.provider.name}' cần {env} trong .env"
    return None


def _strip_role(role: str, msg: str) -> str:
    return msg[len(role) + 2:] if msg.startswith(f"{role}: ") else msg


def check_models(models: dict[str, str] | None, escalate: dict[str, str] | None,
                 providers: dict[str, Provider] | None = None) -> list[str]:
    """Lỗi cấu hình model theo role, rỗng là chạy được. models None: đọc .env (giống missing_keys);
    escalate None: đọc ESCALATE*. Role không có trong `models` thì cũng đọc .env."""
    providers = providers if providers is not None else load_providers()
    problems = []
    for role in ROLES:
        spec = (models or {}).get(role)
        try:
            target = target_for(role, providers, spec=spec)
        except ValueError as e:
            problems.append(f"{role}: {_strip_role(role, str(e))}")
            continue
        if msg := _key_problem(target):
            problems.append(f"{role}: {msg}")
    if escalate is None:
        try:
            escalate = escalation_specs()
        except ValueError as e:
            return problems + [str(e)]
    for role, spec in escalate.items():
        if role not in ESCALATABLE:
            problems.append(f"ESCALATE_{role.upper()}: chỉ dùng được cho {', '.join(ESCALATABLE)}")
            continue
        try:
            target = target_for(role, providers, spec=spec)
        except ValueError as e:
            problems.append(f"{role} (vòng cuối): {_strip_role(role, str(e))}")
            continue
        if msg := _key_problem(target):
            problems.append(f"{role} (vòng cuối): {msg}")
    return problems


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
