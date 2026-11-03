"""Chạy cả team cho một dự án trong projects/<tên>/.

  python main.py --list                                   # liệt kê dự án và provider
  python main.py --project <tên>                          # chạy cả team, model theo MODEL / MODEL_<ROLE> trong .env
  python main.py --project <tên> --model mock             # kịch bản giả, không tốn token
  python main.py --project <tên> --model openai:gpt-5.6   # đổi model mặc định cho lần chạy này
  python main.py --project <tên> --requirements <file.md> # chạy riêng một module của dự án
  python main.py --draw                                   # chỉ in sơ đồ graph
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    from tools.project import list_projects, load_project

    ap = argparse.ArgumentParser(description="Team phần mềm AI agent (PM, BA, Backend, Frontend, Reviewer, Tester)")
    ap.add_argument("--project", default=os.getenv("PROJECT"),
                    help="Tên thư mục trong projects/ (hoặc đặt PROJECT trong .env)")
    ap.add_argument("--requirements", help="File requirements thay cho file khai báo trong project.toml")
    ap.add_argument("--model", metavar="PROVIDER[:MODEL]",
                    help="Một model cho cả team trong lần chạy này, bỏ qua MODEL / MODEL_<ROLE> trong .env. "
                         "'mock': kịch bản giả, không tốn token")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="Không hỏi xác nhận trước khi gọi model thật (bắt buộc khi chạy không có terminal)")
    ap.add_argument("--list", action="store_true", help="Liệt kê dự án trong projects/ và provider trong providers.toml")
    ap.add_argument("--draw", action="store_true", help="Chỉ xuất sơ đồ Mermaid ra docs/graph.mmd")
    args = ap.parse_args()
    if args.model:
        os.environ["MODEL_ALL"] = args.model  # agents/providers: áp cho mọi role, bỏ qua MODEL_<ROLE>

    if args.list:
        from agents.providers import load_providers
        print("Dự án:   " + (", ".join(list_projects()) or "(chưa có; chép projects/_template/ thành projects/<tên>/)"))
        print("Provider: " + ", ".join(f"{n} ({p.type})" for n, p in load_providers().items()))
        return

    from graph import build_graph  # import sau khi đã nạp .env
    app = build_graph()

    mermaid = app.get_graph().draw_mermaid()
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "graph.mmd").write_text(mermaid, encoding="utf-8")
    if args.draw:
        print(mermaid)
        return

    if not args.project:
        have = ", ".join(list_projects()) or "(chưa có; chép projects/_template/ thành projects/<tên>/)"
        sys.exit(f"Cần chọn dự án: --project <tên>. Các dự án hiện có: {have}")
    try:
        project = load_project(args.project, args.requirements)
    except FileNotFoundError as e:
        sys.exit(str(e))
    os.environ["OUTPUT_DIR"] = str(project.output_dir)  # tools/file_tools.py ghi vào đây

    from agents.common import describe_providers
    from tools.file_tools import display
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    from agents.providers import load_providers, parse_spec
    try:
        known = load_providers()
    except ValueError as e:  # providers.toml sai cú pháp hoặc type không hợp lệ
        sys.exit(str(e))
    src = "--model" if os.getenv("MODEL_ALL") else "MODEL"
    default_provider = parse_spec(os.getenv("MODEL_ALL") or os.getenv("MODEL") or "mock")[0]
    if default_provider not in known:  # dừng trước khi gọi bất kỳ model nào
        sys.exit(f"{src}: provider '{default_provider}' chưa khai báo trong providers.toml "
                 f"(có: {', '.join(sorted(known))})")
    models = describe_providers()
    if "=LỖI(" in models:
        sys.exit(f"Cấu hình model chưa đúng:\n   {models}")
    from agents.providers import missing_keys
    if (missing := missing_keys(known)):
        sys.exit("Thiếu API key:\n   " + "\n   ".join(missing))
    from agents.providers import uses_real_model
    if uses_real_model(known) and not args.yes:
        print(f"{project.title}: sẽ gọi model thật (tốn token hoặc hạn mức gói):\n   {models}")
        if not sys.stdin.isatty():
            sys.exit("Không có terminal để xác nhận: thêm --yes để chạy, hoặc --model mock để thử không tốn token.")
        try:
            answer = input("Tiếp tục? [y/N] ")
        except EOFError:  # stdin là NUL (Windows coi là terminal) hoặc bị đóng
            answer = ""
        if answer.strip().lower() not in ("y", "yes", "c", "có"):
            sys.exit("\nĐã hủy. Thêm --yes để chạy không cần hỏi, hoặc --model mock để thử không tốn token.")
    print(f"== Run {run_id} · {project.title} ({display(project.requirements_path)}) · log: runs/{run_id}.jsonl ==")
    print(f"   {models}")
    state = {
        "run_id": run_id, "project": project.name, "project_title": project.title,
        "requirements": project.requirements, "stack": project.stack,
        "tests": {"command": project.test_command, "cwd": project.test_cwd, "timeout": project.test_timeout},
        "log": [],
    }
    final = app.invoke(state, config={"configurable": {"thread_id": run_id}, "recursion_limit": 50})
    print(f"\n== Kết quả: {final.get('final_status')} sau {len(final['log'])} bước, "
          f"{final.get('review_round', 0)} lần trả BA, {final.get('iteration', 0)} vòng test ==")
    print(f"Đầu ra: {display(project.output_dir)}  ·  Log: runs/  ·  Sơ đồ: docs/graph.mmd")


if __name__ == "__main__":
    main()
