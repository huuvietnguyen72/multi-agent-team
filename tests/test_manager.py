"""Quản lý trên giao diện (ui/manager.py) và việc áp lệnh giữa hai bước của graph (ui/runner.py)."""
import threading

import pytest

from agents.common import with_user_input
from graph import build_graph
from state import blocking_findings, notes_for
from tests.test_providers import ROLE_VARS
from tools.run import prepare_run
from ui.manager import Command, build_patch, command_from, mock_reply, validate
from ui.runner import RunControl, stream_events


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ROLE_VARS + ["MODEL_MANAGER"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)


@pytest.fixture
def setup(tmp_path):
    return prepare_run("example", mock=True, output_dir=tmp_path)


STATE = {"review_findings": [{"id": "CR-01", "severity": "required", "owner": "frontend", "detail": "x"}],
         "bugs": [{"id": "BUG-01", "owner": "backend", "detail": "y"}],
         "log": [{"node": "pm_plan", "summary": "a"}, {"node": "reviewer", "summary": "b"}]}


def test_mock_reply_understands_commands():
    assert command_from(mock_reply("bỏ qua CR-1, báo nhầm", STATE)) == \
        Command("dismiss_finding", ["CR-01"], "", "báo nhầm")
    assert command_from(mock_reply("Dừng lại", STATE)).action == "stop"
    assert command_from(mock_reply("chạy tiếp đi", STATE)).action == "resume"
    note = command_from(mock_reply("dặn frontend: hiện lỗi từ trường error", STATE))
    assert (note.action, note.role, note.note) == ("add_note", "frontend", "hiện lỗi từ trường error")
    assert command_from(mock_reply("CR-01 là gì?", STATE)) is None
    assert "CR-01" in mock_reply("CR-01 là gì?", STATE).reply


def test_validate_rejects_unknown_ids_and_roles():
    assert validate(Command("dismiss_finding", ["CR-09"]), STATE) == "không thấy CR-09 trong finding hay bug hiện tại"
    assert validate(Command("dismiss_finding", ["CR-01", "BUG-01"]), STATE) is None
    assert "không nhận ghi chú" in validate(Command("add_note", role="pm", note="x"), STATE)
    assert validate(Command("add_note", role="backend", note=""), STATE) == "ghi chú trống"


def test_dismiss_patch_unblocks_finding():
    patch = build_patch(Command("dismiss_finding", ["CR-01"], note="báo nhầm"), STATE, "reviewer")
    assert blocking_findings({**STATE, **patch}) == []
    assert patch["dismissed"] == {"CR-01": "báo nhầm"} and patch["interventions"][0]["after"] == "reviewer"


def test_note_used_once_by_its_role():
    patch = build_patch(Command("add_note", role="frontend", note="hiện body.error"), STATE, "reviewer")
    state = {**STATE, "manager_notes": patch["manager_notes"]}
    assert "hiện body.error" in with_user_input(state, "frontend", "P")
    assert "hiện body.error" not in with_user_input(state, "backend", "P")
    state["log"] = state["log"] + [{"node": "frontend", "summary": "sửa"}]
    assert notes_for(state, "frontend") == []


def _run_with(setup, on_event):
    """Chạy graph mock, gọi on_event(event, control) sau mỗi sự kiện; trả về danh sách sự kiện."""
    from ui.manager import validate as v
    control = RunControl(apply=lambda cmd, values, after: build_patch(cmd, values, after), validate=v)
    events = []
    for e in stream_events(build_graph(), setup, control=control):
        events.append(e)
        on_event(e, control)
    return events


def test_dismiss_after_review_skips_the_fix(setup, tmp_path):
    pushed = []

    def on_event(e, control):
        if e.kind == "done" and e.node == "reviewer" and not pushed:
            pushed.append(1)
            control.push(Command("dismiss_finding", ["CR-01"], note="báo nhầm"))
    events = _run_with(setup, on_event)
    order = [e.node for e in events if e.kind == "done"]
    first_review = order.index("reviewer")
    assert order[first_review + 1] == "tester"                     # Frontend không bị gửi đi sửa CR-01
    assert [e.kind for e in events].count("applied") == 1
    final = events[-1].final
    assert final["final_status"] == "ACCEPTED" and final["interventions"][0]["text"].startswith("Bỏ qua CR-01")
    report = (tmp_path / "docs" / "final_report.md").read_text(encoding="utf-8")
    assert "Can thiệp của người dùng" in report and "CR-01" in report


def test_pause_then_resume_ends_like_a_normal_run(setup):
    def on_event(e, control):
        if e.kind == "done" and e.node == "pm_plan":
            control.push(Command("stop"))
        if e.kind == "paused":
            threading.Timer(0.2, control.push, args=(Command("resume"),)).start()
    events = _run_with(setup, on_event)
    kinds = [e.kind for e in events]
    assert kinds.count("paused") == 1 and kinds.count("resumed") == 1
    assert kinds.index("paused") < kinds.index("resumed")
    assert kinds.count("done") == 15 and events[-1].final["final_status"] == "ACCEPTED"


def test_rejected_command_changes_nothing(setup):
    def on_event(e, control):
        if e.kind == "done" and e.node == "pm_plan":
            control.push(Command("dismiss_finding", ["CR-77"]))
    events = _run_with(setup, on_event)
    rejected = [e for e in events if e.kind == "rejected"]
    assert len(rejected) == 1 and "CR-77" in rejected[0].message
    assert [e.kind for e in events].count("done") == 15 and not events[-1].final.get("interventions")


def test_ask_manager_mock_and_default_model(monkeypatch):
    from ui.manager import ask_manager, manager_spec
    reply, label = ask_manager("dừng lại", {}, [], spec="mock")
    assert (reply.action, label) == ("stop", "mock")
    assert manager_spec({"pm": "claude-code:sonnet"}) == "claude-code:sonnet"
    monkeypatch.setenv("MODEL_MANAGER", "claude-code:haiku")
    assert manager_spec({"pm": "claude-code:sonnet"}) == "claude-code:haiku"


def test_stop_keeps_last_update(setup):
    stop = threading.Event()
    events = []
    for e in stream_events(build_graph(), setup, stop):
        events.append(e)
        if e.kind == "done" and e.node == "ba":
            stop.set()
    assert [e.node for e in events if e.kind == "done"] == ["pm_plan", "ba"]
    assert events[-1].final.get("user_stories")  # update của bước cuối đã vào checkpoint
