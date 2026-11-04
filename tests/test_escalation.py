"""Quy tắc tự nâng model ở vòng sửa cuối và thông tin model ghi vào log."""
import pytest

from agents.escalation import is_last_fix, pick_target
from agents.providers import load_providers
from tests.test_providers import ROLE_VARS
from tools import runlog


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ROLE_VARS:
        monkeypatch.delenv(k, raising=False)


@pytest.mark.parametrize("role,state,expected", [
    ("ba", {"review_round": 2}, True),
    ("backend", {"code_review_round": 2}, True),
    ("frontend", {"code_review_round": 0, "iteration": 2}, True),
    ("ba", {"review_round": 1}, False),
    ("ba", {}, False),
    ("backend", {"code_review_round": 1}, False),
    ("backend", {"code_review_round": 0, "iteration": 0}, False),
    ("frontend", {"code_review_round": 0, "iteration": 1}, False),
    ("reviewer", {"code_review_round": 2}, False),
    ("tester", {"iteration": 2}, False),
])
def test_is_last_fix_table(role, state, expected):
    assert is_last_fix(role, state) is expected


def _state(normal, last, **counters):
    return {"models": {"backend": normal}, "escalate": {"backend": last}, **counters}


def test_pick_target_escalates_on_last_fix():
    target, before = pick_target("backend", _state("claude-code:sonnet", "claude-code:opus", code_review_round=2),
                                 load_providers())
    assert (target.label, before) == ("claude-code:opus", "claude-code:sonnet")


def test_pick_target_keeps_model_on_other_rounds():
    target, before = pick_target("backend", _state("claude-code:sonnet", "claude-code:opus", code_review_round=1),
                                 load_providers())
    assert (target.label, before) == ("claude-code:sonnet", None)


def test_mock_never_escalates():
    target, before = pick_target("backend", _state("mock", "claude-code:opus", code_review_round=2), load_providers())
    assert (target.label, before) == ("mock", None)


def test_same_model_is_not_reported_as_escalation():
    target, before = pick_target("backend", _state("claude-code:opus", "claude-code:opus", code_review_round=2),
                                 load_providers())
    assert (target.label, before) == ("claude-code:opus", None)


def test_pick_target_reads_env_without_state_maps(monkeypatch):
    monkeypatch.setenv("MODEL", "claude-code")
    monkeypatch.setenv("ESCALATE_FRONTEND", "claude-code:opus")
    target, before = pick_target("frontend", {"code_review_round": 0, "iteration": 2}, load_providers())
    assert (target.label, before) == ("claude-code:opus", "claude-code:sonnet")


def test_log_step_merges_and_clears_call_info(monkeypatch, tmp_path):
    monkeypatch.setattr(runlog, "RUNS", tmp_path)
    info = {"model": "a", "seconds": 1.0, "escalated_from": "b"}
    runlog.set_call_info(info)
    assert runlog.log_step("r", "backend", "x")["data"] == info
    assert runlog.log_step("r", "backend", "y")["data"] == {}
