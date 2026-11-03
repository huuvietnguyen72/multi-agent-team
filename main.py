"""Chạy cả team: python main.py requirements/library_system.md [--mode mock|llm]"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Team phần mềm 5 AI agent")
    ap.add_argument("requirements", nargs="?", default="requirements/library_system.md")
    ap.add_argument("--mode", choices=["mock", "llm"], help="mock: agent giả; llm: gọi Claude")
    ap.add_argument("--draw", action="store_true", help="Chỉ xuất sơ đồ Mermaid ra docs/graph.mmd")
    args = ap.parse_args()
    if args.mode:
        os.environ["AGENT_MODE"] = args.mode

    from graph import build_graph  # import sau khi đã nạp .env
    app = build_graph()

    mermaid = app.get_graph().draw_mermaid()
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "graph.mmd").write_text(mermaid, encoding="utf-8")
    if args.draw:
        print(mermaid)
        return

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"== Run {run_id} · mode={os.getenv('AGENT_MODE', 'mock')} · log: runs/{run_id}.jsonl ==")
    state = {"run_id": run_id, "requirements": (ROOT / args.requirements).read_text(encoding="utf-8"), "log": []}
    final = app.invoke(state, config={"configurable": {"thread_id": run_id}, "recursion_limit": 50})
    print(f"\n== Kết quả: {final.get('final_status')} sau {len(final['log'])} bước, "
          f"{final.get('review_round', 0)} lần trả BA, {final.get('iteration', 0)} vòng test ==")
    print("Đầu ra: output/  ·  Log: runs/  ·  Sơ đồ: docs/graph.mmd")


if __name__ == "__main__":
    main()
