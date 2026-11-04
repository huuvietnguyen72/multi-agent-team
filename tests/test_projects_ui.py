"""Tạo và sửa dự án từ giao diện (ui/projects.py, tools/project.write_project)."""
import json
import sqlite3

import pytest

from tools.project import load_project, slugify, write_project
from ui.history import ensure_schema
from ui.projects import description, draft_project, mock_draft, runs_of, threads_of, unique_slug


def test_slugify():
    assert slugify("Quản lý kho Đồ ăn!") == "quan-ly-kho-do-an"
    assert slugify("!!!") == "du-an"


def test_write_project_create_and_edit(tmp_path):
    p = write_project("kho", title='Kho "A"', requirements="# Kho\n\n## Mô tả\nQuản lý hàng.\n", stack="- FastAPI",
                      test_command="python -m pytest -q", base=tmp_path, create=True)
    assert p.title == 'Kho "A"' and p.test_command == "python -m pytest -q" and p.test_cwd == "backend"
    with pytest.raises(FileExistsError):
        write_project("kho", title="x", requirements="r", stack="s", base=tmp_path, create=True)
    with pytest.raises(ValueError):
        write_project("Kho Hàng", title="x", requirements="r", stack="s", base=tmp_path, create=True)
    with pytest.raises(ValueError):
        write_project("trong", title="x", requirements=" ", stack="s", base=tmp_path, create=True)
    (tmp_path / "kho" / "project.toml").write_text(
        (tmp_path / "kho" / "project.toml").read_text(encoding="utf-8").replace("[tests]", 'output = "build"\n\n[tests]\ntimeout = 99'),
        encoding="utf-8")
    p = write_project("kho", title="Kho B", requirements="# mới", stack="- Flask", base=tmp_path)
    assert p.title == "Kho B" and p.requirements.strip() == "# mới" and p.test_command is None
    assert p.output_dir.name == "build" and p.test_timeout == 99      # khóa khác trong project.toml được giữ


def test_unique_slug(tmp_path):
    (tmp_path / "kho").mkdir()
    assert unique_slug("Kho", base=tmp_path) == "kho-2"


def test_mock_draft_and_draft_project_with_mock():
    d = mock_draft("Quản lý kho. Nhân viên nhập xuất hàng.")
    assert d.title == "Quản lý kho" and d.slug == "quan-ly-kho" and "# Quản lý kho" in d.requirements
    assert "## Business rules" in d.requirements and "## Backend" in d.stack
    again = mock_draft("thêm chức năng báo cáo", previous=d.model_dump())
    assert again.requirements == d.requirements
    draft, label = draft_project("Quản lý kho", spec="mock")
    assert label.startswith("mock") and draft.slug == "quan-ly-kho"


def test_description_runs_and_threads(tmp_path):
    assert "mỗi người ghi lại" in description("example")
    (tmp_path / "r2.ui.json").write_text(json.dumps({"run_id": "r2", "project": "example",
                                                     "values": {"final_status": "ACCEPTED"}}), encoding="utf-8")
    (tmp_path / "r1.ui.json").write_text(json.dumps({"run_id": "r1", "project": "khac", "values": {}}), encoding="utf-8")
    assert runs_of("example", runs_dir=tmp_path) == [{"run_id": "r2", "status": "ACCEPTED"}]
    db = tmp_path / "h.db"
    ensure_schema(db)
    with sqlite3.connect(db) as con:
        con.executemany('INSERT INTO threads ("id","name","userIdentifier","tags","createdAt") VALUES (?,?,?,?,?)',
                        [("t1", "A", "admin", '["example"]', "2026-11-04T10:00"),
                         ("t2", "B", "admin", '["khac"]', "2026-11-04T11:00"),
                         ("t3", "C", "binh", '["example"]', "2026-11-04T12:00")])
    assert [t["id"] for t in threads_of("example", "admin", db_path=db)] == ["t1"]
    assert threads_of("example", "admin", db_path=tmp_path / "khong-co.db") == []


def test_example_project_still_loads():
    assert load_project("example").title.startswith("Ví dụ")
