"""Tự nâng model ở vòng sửa cuối: BA, Backend, Frontend được đổi sang model mạnh hơn ở lần sửa cuối cùng
trước khi hết MAX_ROUNDS (bảng "Vòng sửa cuối" trong Spec)."""
from __future__ import annotations

from typing import Mapping

from agents.providers import ESCALATABLE, Provider, Target, escalation_specs, target_for
from state import MAX_ROUNDS


def is_last_fix(role: str, state: Mapping) -> bool:
    last = MAX_ROUNDS - 1
    if role == "ba":
        return state.get("review_round", 0) == last
    if role in ("backend", "frontend"):
        review = state.get("code_review_round", 0)
        return review == last or (review == 0 and state.get("iteration", 0) == last)
    return False


def pick_target(role: str, state: Mapping,
                providers: dict[str, Provider] | None = None) -> tuple[Target, str | None]:
    """(target cho lần gọi này, label của model thường nếu đã đổi sang model vòng cuối, không thì None)."""
    normal = target_for(role, providers, spec=(state.get("models") or {}).get(role))
    if role not in ESCALATABLE or normal.provider.type == "mock" or not is_last_fix(role, state):
        return normal, None
    last = (state.get("escalate") or {}).get(role) if "escalate" in state else escalation_specs().get(role)
    if not last:
        return normal, None
    stronger = target_for(role, providers, spec=last)
    if stronger.label == normal.label:
        return normal, None
    return stronger, normal.label
