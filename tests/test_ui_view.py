"""Nội dung hiển thị của giao diện (ui/view.py), chạy với kịch bản mock."""
import pytest

from graph import build_graph
from tests.test_providers import ROLE_VARS
from tools.run import prepare_run
from ui.view import (Progress, changed_files, files_for, language_for, message_for, redact, snapshot,
                     summary_text)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ROLE_VARS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def mock_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL", "mock")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    app = build_graph()
    out = []
    for chunk in app.stream({"run_id": "pytest-view", "requirements": "x", "log": []},
                            {"configurable": {"thread_id": "pytest-view"}}, stream_mode="updates"):
        for node, upd in chunk.items():
            out.append((node, upd))
    assert len(out) == 15
    return out


def test_message_for_every_mock_step(mock_updates):
    msgs = [(node, message_for(node, upd)) for node, upd in mock_updates]
    assert all(m.strip() and "_model:_" not in m for _, m in msgs)  # chạy mock: không có dòng model, thời gian
    assert "CR-01" in next(m for n, m in msgs if n == "reviewer")
    assert "BUG-01" in next(m for n, m in msgs if n == "tester")
    assert "ACCEPTED" in next(m for n, m in msgs if n == "pm_accept")


def test_message_shows_escalation():
    upd = {"log": [{"node": "backend", "summary": "sửa 1 finding review, ghi 2 file",
                    "data": {"model": "claude-code:opus", "seconds": 12.3, "escalated_from": "claude-code:sonnet"}}]}
    m = message_for("backend", upd)
    assert "claude-code:sonnet" in m and "claude-code:opus" in m and "vòng sửa cuối" in m


def test_progress_follows_mock_run(mock_updates):
    p = Progress()
    for node, upd in mock_updates:
        p.start(node)
        p.finish(node, upd)
    rows = p.rows()
    assert all(st == "done" for _, st in rows)
    titles = [t for t, _ in rows]
    assert "Review code (vòng 1/3)" in titles
    assert "Kiểm thử (vòng 2/3)" in titles


def test_progress_returns_row_to_running():
    p = Progress()
    p.start("frontend")
    p.finish("frontend", {})
    p.start("frontend")
    assert dict((t, s) for t, s in p.rows())["Frontend"] == "running"
    p.start("tester")
    p.fail("tester")
    assert [s for t, s in p.rows() if t.startswith("Kiểm thử")] == ["failed"]


def test_changed_files_ignores_untouched_and_missing_dir(tmp_path):
    assert snapshot(tmp_path / "chua-co") == {}
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    s1 = snapshot(tmp_path)
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    s2 = snapshot(tmp_path)
    assert changed_files(s1, s2) == [tmp_path / "b.md"]
    (tmp_path / "a.md").write_text("dài hơn", encoding="utf-8")
    assert tmp_path / "a.md" in changed_files(s2, snapshot(tmp_path))


def test_files_for_splits_parallel_devs(tmp_path):
    files = [tmp_path / "backend" / "pom.xml", tmp_path / "frontend" / "index.html",
             tmp_path / "docs" / "api_spec.md", tmp_path / "docs" / "code_review_test1_round1.md"]
    assert files_for("backend", files, tmp_path) == [files[0], files[2]]
    assert files_for("frontend", files, tmp_path) == [files[1]]
    assert files_for("reviewer", files, tmp_path) == [files[3]]


def test_language_for():
    assert language_for("A.java") == "java"
    assert language_for("app.JS") == "javascript"
    assert language_for("notes.txt") is None


def test_redact_hides_key_values():
    assert redact("401: key sk-abc12345xyz invalid", ["sk-abc12345xyz", "", "abc"]) == "401: key *** invalid"


def test_summary_text_mock(tmp_path, monkeypatch):
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    setup = prepare_run("library", mock=True, output_dir=tmp_path)
    final = build_graph().invoke(setup.state, setup.config)
    text = summary_text(final, setup, 75.0)
    assert "ACCEPTED" in text and "15 bước" in text
    assert f"runs/{setup.run_id}.jsonl" in text and "cả team=`mock`" in text
