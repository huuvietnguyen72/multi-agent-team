"""Ghi mỗi bước vào runs/<run_id>.jsonl để làm báo cáo."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"


def log_step(run_id: str, node: str, summary: str, data: dict | None = None) -> dict:
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "node": node,
             "summary": summary, "data": data or {}}
    RUNS.mkdir(exist_ok=True)
    with open(RUNS / f"{run_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['time']}] {node:<10} {summary}")
    return entry
