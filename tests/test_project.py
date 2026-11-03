"""Kiểm tra cấu trúc dự án (projects/<tên>/), việc chèn stack vào prompt, lệnh test tự động,
và việc skills/mock không còn gắn với một đề cụ thể."""
import re
import sys
from pathlib import Path

import pytest

from agents import common
from tools.project import PROJECTS, list_projects, load_project
from tools.test_runner import run_project_tests

ROOT = Path(__file__).resolve().parent.parent


def test_list_projects_hides_template():
    names = list_projects()
    assert {"library", "library-borrow-detail"} <= set(names)
    assert "_template" not in names


def test_load_project_reads_config_and_files():
    p = load_project("library")
    assert p.title == "Hệ thống mượn sách thư viện"
    assert "Spring Boot" in p.stack and "BR-01" in p.requirements
    assert p.test_command == "mvn -q -B test" and p.test_cwd == "backend"
    assert p.output_dir == (PROJECTS / "library" / "output").resolve()


def test_template_is_loadable_and_has_no_test_command():
    p = load_project("_template")
    assert p.test_command is None and "<Tên hệ thống>" in p.requirements


def test_requirements_override_and_missing_project(tmp_path):
    other = tmp_path / "module.md"
    other.write_text("# Module X", encoding="utf-8")
    assert load_project("library", requirements=other).requirements == "# Module X"
    with pytest.raises(FileNotFoundError, match="library"):  # thông báo liệt kê dự án hiện có
        load_project("khong-ton-tai")


def test_stack_is_prepended_to_prompt_for_real_providers(monkeypatch):
    seen = {}
    monkeypatch.setenv("MODEL", "claude-api:any-model")
    monkeypatch.setattr(common, "adapter",
                        lambda kind: lambda target, role, prompt, schema: seen.setdefault("prompt", prompt))
    state = {"stack": "- FastAPI + SQLite", "project_title": "Demo"}
    common.ask("backend", "backend", state, "User stories: ...", object)
    assert seen["prompt"].startswith("# Stack và quy ước kỹ thuật của Demo\n\n- FastAPI + SQLite")
    assert seen["prompt"].endswith("User stories: ...")
    assert common.with_project_context({}, "x") == "x"  # không có stack thì giữ nguyên prompt


def test_project_test_command(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    (tmp_path / "backend").mkdir()
    tests = {"command": f'"{sys.executable}" -c "print(\'tests ok\')"', "cwd": "backend", "timeout": 60}
    monkeypatch.delenv("RUN_TESTS", raising=False)
    monkeypatch.delenv("RUN_MVN", raising=False)
    assert run_project_tests(tests) is None  # chưa bật RUN_TESTS
    monkeypatch.setenv("RUN_TESTS", "1")
    out = run_project_tests(tests)
    assert "exit code 0" in out and "tests ok" in out
    assert "chưa khai báo" in run_project_tests({"command": None})
    assert "chưa được sinh ra" in run_project_tests({"command": "echo", "cwd": "frontend"})


# Từ chỉ có trong đề thư viện hoặc stack Java cụ thể: skills và mock phải dùng được cho mọi dự án.
DOMAIN_TERMS = ["thư viện", "mượn", "cuốn", "thủ thư", "sinh viên", "Spring", "JUnit", "Maven", "mvn",
                "com.example", "BR-05", "localhost"]


@pytest.mark.parametrize("path", sorted((ROOT / "skills").glob("*/SKILL.md")) + [ROOT / "agents" / "mock.py"],
                         ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_project_specific_terms(path):
    text = path.read_text(encoding="utf-8")
    found = [t for t in DOMAIN_TERMS if re.search(re.escape(t), text, flags=re.IGNORECASE)]
    if path.name == "mock.py":
        found = [t for t in found if t != "localhost"]  # mock ghi API_BASE minh họa
    assert not found, f"{path.relative_to(ROOT)} còn từ gắn với một dự án cụ thể: {found}"
