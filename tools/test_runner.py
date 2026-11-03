"""Chạy `mvn test` cho backend agent sinh ra (bật bằng RUN_MVN=1)."""
from __future__ import annotations

import os
import shutil
import subprocess

from tools.file_tools import OUTPUT


def run_maven_tests(timeout: int = 600) -> str | None:
    if os.getenv("RUN_MVN") != "1":
        return None
    mvn = shutil.which("mvn") or shutil.which("mvn.cmd")
    if not mvn:
        return "mvn không có trên PATH, bỏ qua chạy test."
    backend = OUTPUT / "backend"
    if not (backend / "pom.xml").exists():
        return "Không có output/backend/pom.xml: backend chưa sinh project Maven."
    try:
        proc = subprocess.run([mvn, "-q", "-B", "test"], cwd=backend, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"mvn test quá {timeout}s."
    out = (proc.stdout + proc.stderr)[-8000:]
    return f"exit code {proc.returncode}\n{out}"
