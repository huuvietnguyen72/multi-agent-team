"""Chạy graph ở luồng nền và phát sự kiện (ui/runner.py), với kịch bản mock."""
import threading

import pytest

from graph import build_graph
from tests.test_providers import ROLE_VARS
from tools.run import prepare_run
from ui.runner import Event, exclusive_run, stream_events


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ROLE_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)


@pytest.fixture
def setup(tmp_path):
    return prepare_run("example", mock=True, output_dir=tmp_path)


def test_events_cover_mock_run(setup):
    events = list(stream_events(build_graph(), setup))
    kinds = [e.kind for e in events]
    assert kinds.count("start") == 15 and kinds.count("done") == 15
    assert events[-1].kind == "end" and events[-1].final["final_status"] == "ACCEPTED"
    idx = {(e.kind, e.node): i for i, e in reversed(list(enumerate(events)))}  # lần xuất hiện đầu tiên
    first_done = min(idx[("done", "backend")], idx[("done", "frontend")])
    assert idx[("start", "backend")] < first_done and idx[("start", "frontend")] < first_done


def test_error_event_names_failing_node(setup, monkeypatch):
    from agents import mock

    def boom(state):
        raise RuntimeError("hết hạn mức")
    monkeypatch.setattr(mock, "tester", boom)
    events = list(stream_events(build_graph(), setup))
    err = [e for e in events if e.kind == "error"]
    assert len(err) == 1 and err[0].node == "tester" and "hết hạn mức" in err[0].message
    assert events[events.index(err[0]) + 1].kind == "end"
    assert not any(e.kind == "done" and e.node == "tester" for e in events)


def test_stop_ends_after_current_step(setup):
    stop = threading.Event()
    events = []
    for e in stream_events(build_graph(), setup, stop):
        events.append(e)
        if e.kind == "done":
            stop.set()
    assert [e.node for e in events if e.kind == "done"] == ["pm_plan"]
    assert events[-1].kind == "end" and "plan" in events[-1].final


def test_second_run_is_refused_while_first_runs():
    with exclusive_run() as a, exclusive_run() as b:
        assert a is True and b is False
    with exclusive_run() as c:
        assert c is True


def test_event_is_plain_data():
    assert Event("start", "ba") == Event("start", "ba")
