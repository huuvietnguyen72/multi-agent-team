"""Kiểm tra agents/claude_code.py bằng tiến trình giả (không gọi `claude` thật, không tốn hạn mức)."""
import json
import subprocess

import pytest

from agents import claude_code
from schemas import PMReview


def _fake_run(outputs, calls):
    def run(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout=outputs.pop(0), stderr="")
    return run


def _ok(structured):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "stop_reason": "end_turn", "structured_output": structured})


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    calls = []

    def install(*outputs):
        monkeypatch.setattr(claude_code.subprocess, "run", _fake_run(list(outputs), calls))
        return calls
    return install


def test_parses_structured_output_and_uses_subscription(fake):
    calls = fake(_ok({"approved": True, "review_notes": "ok"}))
    out = claude_code.call_structured("pm", "duyệt đi", PMReview)
    assert out == PMReview(approved=True, review_notes="ok")
    cmd, kw = calls[0]
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--tools") + 1] == ""
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["title"] == "PMReview"
    assert cmd[cmd.index("--system-prompt-file") + 1].replace("\\", "/").endswith("skills/pm/SKILL.md")
    assert kw["input"] == "duyệt đi"
    assert "ANTHROPIC_API_KEY" not in kw["env"]  # không để key (kể cả rỗng) đè lên đăng nhập thuê bao


def test_retries_once_on_bad_schema(fake):
    calls = fake(_ok({"approved": "không rõ"}), _ok({"approved": False, "review_notes": "thiếu BR-03"}))
    assert claude_code.call_structured("pm", "x", PMReview).approved is False
    assert len(calls) == 2


def test_error_result_raises(fake):
    fake(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "usage limit reached"}))
    with pytest.raises(RuntimeError, match="usage limit"):
        claude_code.call_structured("pm", "x", PMReview)
