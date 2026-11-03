"""Chạy lệnh test tự động của dự án (khai báo ở [tests] trong project.toml) trên code agent sinh ra.

Chỉ chạy khi RUN_TESTS=1 (RUN_MVN=1 vẫn được chấp nhận cho cấu hình cũ). Kết quả đưa cho Tester làm bằng chứng.
Lệnh lấy từ project.toml do chính bạn viết, chạy qua shell trong <output>/<cwd>.
"""
from __future__ import annotations

import os
import subprocess

from tools.file_tools import display, output_dir


def tests_enabled() -> bool:
    return os.getenv("RUN_TESTS") == "1" or os.getenv("RUN_MVN") == "1"


def run_project_tests(tests: dict | None) -> str | None:
    """`tests` = {"command", "cwd", "timeout"} lấy từ state. Trả output (đã cắt) hoặc None nếu không chạy."""
    if not tests_enabled():
        return None
    command = (tests or {}).get("command")
    if not command:
        return "Dự án chưa khai báo [tests].command trong project.toml, bỏ qua chạy test."
    cwd = (output_dir() / tests.get("cwd", ".")).resolve()
    if not cwd.is_dir():
        return f"Không có thư mục {display(cwd)}: code chưa được sinh ra, bỏ qua chạy test."
    timeout = int(tests.get("timeout", 600))
    try:
        proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"`{command}` chạy quá {timeout}s."
    out = (proc.stdout + proc.stderr)[-8000:]
    return f"$ {command}  (trong {display(cwd)})\nexit code {proc.returncode}\n{out}"
