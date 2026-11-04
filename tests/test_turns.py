"""Lượt làm việc của từng role và phần sửa từng file (ui/turns.py)."""
import time

import pytest

from graph import build_graph
from tests.test_providers import ROLE_VARS
from tools.run import prepare_run
from ui.runner import stream_events
from ui.turns import MAX_DIFF_LINES, Turns, diff_file, file_changes, turn_task
from ui.view import snapshot


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ROLE_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)


def test_diff_file_new_file_is_all_added():
    fc = diff_file("a.py", None, "x\ny\n")
    assert fc.new_file and (fc.added, fc.removed) == (2, 0)
    assert [l.kind for l in fc.lines if l.kind != "hunk"] == ["add", "add"]


def test_diff_file_one_changed_line_has_context_and_numbers():
    old = "\n".join(f"line {i}" for i in range(1, 21))
    new = old.replace("line 10", "line 10 sửa")
    fc = diff_file("a.py", old, new)
    kinds = [l.kind for l in fc.lines]
    assert kinds == ["hunk"] + ["ctx"] * 3 + ["del", "add"] + ["ctx"] * 3
    dl = next(l for l in fc.lines if l.kind == "del")
    al = next(l for l in fc.lines if l.kind == "add")
    assert (dl.old, dl.new, dl.text) == (10, None, "line 10")
    assert (al.old, al.new, al.text) == (None, 10, "line 10 sửa")
    first_ctx = fc.lines[1]
    assert (first_ctx.old, first_ctx.new) == (7, 7)
    assert (fc.added, fc.removed) == (1, 1)


def test_diff_file_truncates_long_diffs():
    fc = diff_file("a.py", None, "\n".join(str(i) for i in range(1000)))
    assert len(fc.lines) == MAX_DIFF_LINES and fc.truncated
    assert fc.added == 1000


def test_diff_file_without_content_explains_why():
    fc = diff_file("logo.png", "", None)
    assert fc.lines == [] and fc.note


def test_turn_task_cases():
    assert turn_task("backend", {}) == ("Bản đầu", None)
    cr = {"code_review_round": 1, "review_findings": [{"id": "CR-01", "severity": "required", "owner": "frontend"}]}
    assert turn_task("frontend", cr) == ("Sửa CR-01", "Reviewer vòng 1/3")
    bug = {"code_review_round": 0, "iteration": 2,
           "bugs": [{"id": "BUG-02", "ref": "BR-03", "owner": "backend"}]}
    assert turn_task("backend", bug) == ("Sửa BUG-02 (BR-03)", "Tester vòng 2/3")
    assert turn_task("ba", {"review_round": 1}) == ("Sửa theo góp ý của PM", "PM vòng 1/3")


def test_mock_turns_cover_fixes(tmp_path):
    setup = prepare_run("library", mock=True, output_dir=tmp_path)
    turns, before, phases = Turns(), {}, {}
    for e in stream_events(build_graph(), setup):
        now = time.monotonic()
        if e.kind == "start":
            turns.start(e.node, e.data or {}, now)
            before[e.node] = snapshot(tmp_path)
            phases[e.node] = []
        elif e.kind == "progress":
            turns.progress(e.node, e.data)
            phases[e.node].append(e.data["phase"])
        elif e.kind == "done":
            assert "model" in phases[e.node], e.node
            files = file_changes(e.node, before.pop(e.node), snapshot(tmp_path), tmp_path)
            turns.finish(e.node, files, (e.update.get("log") or [{}])[-1].get("data", {}), now)
    fe = turns.of("Frontend")
    assert [t.n for t in fe] == [2, 1] and fe[0].task == "Sửa CR-01"
    app_js = next(f for f in fe[0].files if f.path == "frontend/app.js")
    assert app_js.added >= 1 and app_js.removed >= 1
    be = turns.of("Backend")
    assert len(be) == 2 and be[0].task == "Sửa BUG-01 (BR-01)"
    assert all(t.status == "done" and t.model == "mock" for t in turns.all)
