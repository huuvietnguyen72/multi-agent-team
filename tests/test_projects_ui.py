"""Tạo và sửa dự án từ giao diện (ui/projects.py, tools/project.write_project)."""
import json
import sqlite3

import pytest

from tools.project import list_modules, load_module, load_project, module_requirements, slugify, write_module, \
    write_project
from tools.run import archive_output, prepare_run
from ui.history import ensure_schema
from ui.projects import description, draft_module, draft_project, mock_draft, mock_module, modules_of, runs_of, \
    threads_of, unique_slug


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
    assert runs_of("example", runs_dir=tmp_path) == [{"run_id": "r2", "module": None, "status": "ACCEPTED"}]
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


def _project(tmp_path, out_files=None):
    write_project("shop", title="Shop", requirements="# Shop\n\n## Business rules\n\nBR-01 ...", stack="## Backend\n",
                  base=tmp_path, create=True)
    for rel, text in (out_files or {}).items():
        f = tmp_path / "shop" / "output" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")


def test_modules_write_list_and_requirements(tmp_path):
    _project(tmp_path)
    assert list_modules("shop", base=tmp_path) == []
    m = write_module("shop", "gio-hang", title="Giỏ hàng", requirements="# Bất kỳ\n\n## Mục tiêu\n\nThêm giỏ.",
                     base=tmp_path, create=True)
    assert m.title == "Giỏ hàng" and m.requirements.startswith("# Module: Giỏ hàng\n\n## Mục tiêu")
    with pytest.raises(FileExistsError):
        write_module("shop", "gio-hang", title="X", requirements="y", base=tmp_path, create=True)
    with pytest.raises(ValueError):
        write_module("shop", "Giỏ", title="X", requirements="y", base=tmp_path)
    write_module("shop", "gio-hang", title="Giỏ hàng 2", requirements="## Mục tiêu\n\nSửa.", base=tmp_path)
    assert [x.title for x in list_modules("shop", base=tmp_path)] == ["Giỏ hàng 2"]
    text = module_requirements(load_project("shop", base=tmp_path), load_module("shop", "gio-hang", base=tmp_path))
    assert text.index("# Module: Giỏ hàng 2") < text.index("Bối cảnh") < text.index("BR-01")


def test_module_run_keeps_existing_code(tmp_path, monkeypatch):
    import tools.project as tp
    monkeypatch.setattr(tp, "PROJECTS", tmp_path)
    monkeypatch.setenv("OUTPUT_DIR", "")  # prepare_run đặt biến này; trả lại sau test
    _project(tmp_path, {"backend/app/main.py": "x = 1\n", "backend/node_modules/a.js": "skip",
                        "frontend/app.js": "y", "docs/api_spec.md": "GET /items"})
    write_module("shop", "gio-hang", title="Giỏ hàng", requirements="## Mục tiêu\n\nGiỏ.", base=tmp_path)
    setup = prepare_run("shop", mock=True, module="gio-hang")
    st = setup.state
    assert st["module"] == "gio-hang" and st["module_title"] == "Giỏ hàng"
    assert st["requirements"].startswith("# Module: Giỏ hàng")
    assert [p.rsplit("/", 1)[-1] for p in st["backend_code"]] == ["main.py"]
    assert len(st["frontend_code"]) == 1 and st["api_spec"] == "GET /items"
    out = tmp_path / "shop" / "output"
    moved = archive_output(out, "r2", keep=True)
    assert (moved / "backend" / "app" / "main.py").is_file() and (out / "backend" / "app" / "main.py").is_file()
    assert not (moved / "backend" / "node_modules").exists()
    with pytest.raises(FileNotFoundError):
        prepare_run("shop", mock=True, module="khong-co")


def test_module_scope_in_prompt():
    from agents.common import with_scope
    assert with_scope({}, "P") == "P"
    text = with_scope({"module": "gio-hang", "module_title": "Giỏ hàng"}, "P")
    assert "module Giỏ hàng" in text and text.endswith("P") and "nội dung đầy đủ" in text


def test_mock_module_and_modules_of(tmp_path):
    d = mock_module("Giỏ hàng: thêm, xóa sản phẩm")
    assert d.title == "Giỏ hàng" and d.slug == "gio-hang" and "## Business rules" in d.requirements
    draft, label = draft_module("example", "Giỏ hàng", spec="mock")
    assert label.startswith("mock") and draft.slug == "gio-hang"
    _project(tmp_path)
    write_module("shop", "gio-hang", title="Giỏ hàng", requirements="## Mục tiêu\n\nGiỏ.", base=tmp_path)
    write_module("shop", "admin", title="Admin", requirements="## Mục tiêu\n\nAdmin.", base=tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "r1.ui.json").write_text(json.dumps({"run_id": "r1", "project": "shop", "values": {
        "module": "gio-hang", "final_status": "ACCEPTED"}}), encoding="utf-8")
    db = tmp_path / "h.db"
    ensure_schema(db)
    with sqlite3.connect(db) as con:
        con.execute('INSERT INTO threads ("id","name","userIdentifier","tags","createdAt") VALUES (?,?,?,?,?)',
                    ("t1", "Giỏ hàng", "admin", '["shop", "module:gio-hang"]', "2026-11-04T10:00"))
    got = {m["name"]: m for m in modules_of("shop", "admin", runs_dir=runs, db_path=db, base=tmp_path)}
    assert got["gio-hang"]["status"] == "ACCEPTED" and got["gio-hang"]["thread"] == "t1"
    assert got["admin"]["status"] is None and got["admin"]["thread"] is None
    assert unique_slug("gio-hang", base=tmp_path / "shop" / "modules", suffix=".md") == "gio-hang-2"
