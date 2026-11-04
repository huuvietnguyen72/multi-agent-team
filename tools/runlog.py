"""Ghi mỗi bước vào runs/<run_id>.jsonl để làm báo cáo."""
from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"

# Thông tin lần gọi model gần nhất của node đang chạy. ContextVar nên Backend và Frontend chạy song song
# (mỗi node một luồng, LangGraph chép context riêng) không ghi lẫn của nhau.
_CALL_INFO: ContextVar[dict | None] = ContextVar("call_info", default=None)


def set_call_info(info: dict) -> None:
    """{"model", "seconds", "escalated_from" (chỉ khi đã đổi model)}; log_step() kế tiếp gộp vào data rồi xóa."""
    _CALL_INFO.set(dict(info))


def log_step(run_id: str, node: str, summary: str, data: dict | None = None) -> dict:
    info = _CALL_INFO.get()
    _CALL_INFO.set(None)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "node": node,
             "summary": summary, "data": {**(data or {}), **(info or {})}}
    RUNS.mkdir(exist_ok=True)
    with open(RUNS / f"{run_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['time']}] {node:<10} {summary}")
    return entry
