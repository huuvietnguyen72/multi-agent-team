"""Lưu/đọc lại lượt chạy, bảng SQLite cho lịch sử chat, và dữ liệu khung Mã nguồn."""
import asyncio
import sqlite3

import pytest

from ui.code import read_file, source_for_run, sources, tree
from ui.history import (check_login, decode_row, encode_params, ensure_schema, load_run, save_run)
from ui.turns import Turns, diff_file


def test_save_and_load_run_keeps_state_and_turns(tmp_path):
    turns = Turns()
    turns.start("backend", {}, 0.0)
    turns.finish("backend", [diff_file("backend/A.java", None, "class A {}\n")], {"model": "mock"}, 2.0)
    turns.start("tester", {}, 3.0)  # còn chạy khi lưu (app tắt giữa chừng)
    save_run("r1", {"final_status": "ACCEPTED", "bugs": []}, turns, project="example", runs_dir=tmp_path)
    values, loaded = load_run("r1", runs_dir=tmp_path)
    assert values["final_status"] == "ACCEPTED"
    backend = loaded.of("Backend")[0]
    assert backend.files[0].path == "backend/A.java" and backend.files[0].lines[-1].kind == "add"
    assert loaded.of("Tester")[0].status == "failed"
    assert loaded.props("Backend", 10.0)["turns"][0]["added"] == 1
    assert load_run("khong-co", runs_dir=tmp_path) is None


def test_schema_and_json_params(tmp_path):
    db = tmp_path / "h.db"
    ensure_schema(db)
    ensure_schema(db)  # chạy lại không lỗi
    with sqlite3.connect(db) as con:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "threads", "steps", "elements", "feedbacks"} <= names
    assert encode_params({"tags": ["a"], "x": 1}) == {"tags": '["a"]', "x": 1}
    assert decode_row({"thread_metadata": '{"a": 1}', "output": '{"a": 1}'}) == {"thread_metadata": {"a": 1},
                                                                                   "output": '{"a": 1}'}


def test_data_layer_roundtrip(tmp_path):
    pytest.importorskip("aiosqlite")
    pytest.importorskip("chainlit")
    from chainlit.user import User
    from ui.history import make_data_layer

    async def run():
        dl = make_data_layer(tmp_path / "h.db")
        user = await dl.create_user(User(identifier="admin", metadata={"role": "admin"}))
        await dl.update_thread("t1", name="Ví dụ · r1", user_id=user.id, metadata={"run_ref": {"run_id": "r1"}},
                               tags=["x"])
        thread = await dl.get_thread("t1")
        await dl.engine.dispose()
        return thread

    thread = asyncio.run(run())
    assert thread["name"] == "Ví dụ · r1" and thread["metadata"]["run_ref"]["run_id"] == "r1"
    assert thread["tags"] == ["x"]


def test_login(monkeypatch):
    monkeypatch.delenv("UI_USERNAME", raising=False)
    monkeypatch.delenv("UI_PASSWORD", raising=False)
    assert check_login("admin", "admin") and not check_login("admin", "x")
    monkeypatch.setenv("UI_USERNAME", "viet")
    monkeypatch.setenv("UI_PASSWORD", "bi-mat")
    assert check_login("viet", "bi-mat") and not check_login("admin", "admin")


def test_code_sources_tree_and_read(tmp_path):
    out = tmp_path / "output"
    (out / "backend" / "src").mkdir(parents=True)
    (out / "backend" / "src" / "A.java").write_text("class A {}")
    (out / "frontend" / "node_modules" / "x").mkdir(parents=True)
    (out / "frontend" / "node_modules" / "x" / "i.js").write_text("")
    (out / "frontend" / "app.js").write_text("let a = 1;")
    (tmp_path / ".output_run").write_text("r2")
    old = tmp_path / "output_history" / "r1"
    old.mkdir(parents=True)
    (old / "README.md").write_text("# cũ")

    items = sources(out)
    assert [s["id"] for s in items] == ["output", "r1"] and items[0]["label"] == "Lượt r2 (mới nhất)"
    assert source_for_run(out, "r1") == "r1" and source_for_run(out, "r2") == "output"
    assert source_for_run(out, "da-xoa") == "output"
    files, truncated = tree(out)
    assert [f["path"] for f in files] == ["backend/src/A.java", "frontend/app.js"] and not truncated
    assert read_file(out, "frontend/app.js") == ("let a = 1;", "javascript")
    assert read_file(out, "../.output_run") is None       # không ra ngoài thư mục đầu ra
    assert read_file(out, "khong-co.txt") is None
