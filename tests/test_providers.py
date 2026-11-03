"""Kiểm tra lớp provider: chọn model theo role, đọc providers.toml, và 3 adapter bằng tiến trình/HTTP/SDK giả
(không gọi model thật, không cần key, không tốn hạn mức)."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from agents import providers
from agents.providers import Provider, Target, describe, load_providers, parse_spec, target_for
from agents.providers import anthropic_api, claude_code, openai_compat
from schemas import PMReview

ROLE_VARS = ["MODEL", "MODEL_ALL"] + [f"{k}_{r.upper()}" for k in ("MODEL", "EFFORT", "MAX_TOKENS") for r in providers.ROLES] + \
            ["EFFORT", "MAX_TOKENS"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Không để .env của máy (đã nạp khi chạy main) ảnh hưởng tới test."""
    for k in ROLE_VARS:
        monkeypatch.delenv(k, raising=False)


def t(kind="openai-compatible", model="m", effort=None, max_tokens=None, name="p", role="pm", **opts):
    return Target(role, Provider(name, kind, opts), model, effort, max_tokens)


# ---------- chọn model theo role ----------

def test_parse_spec_keeps_colons_in_model_name():
    assert parse_spec("ollama:qwen3:8b") == ("ollama", "qwen3:8b")
    assert parse_spec("claude-code") == ("claude-code", None)


def test_bundled_providers_cover_each_adapter():
    ps = load_providers()
    assert {ps[n].type for n in ("claude-code", "claude-api", "opencode-go", "mock")} == \
        {"claude-code", "anthropic", "openai-compatible", "mock"}
    for p in ps.values():
        assert "api_key" not in p.options, f"{p.name}: key phải nằm trong .env, không ghi vào providers.toml"


def test_target_resolution(monkeypatch):
    ps = load_providers()
    assert target_for("pm", ps).provider.type == "mock"           # chưa đặt gì: mock, không tốn token
    monkeypatch.setenv("MODEL", "claude-code")
    monkeypatch.setenv("MODEL_BACKEND", "opencode-go:glm-5.3")
    monkeypatch.setenv("MAX_TOKENS_BACKEND", "131072")
    pm, be = target_for("pm", ps), target_for("backend", ps)
    assert (pm.label, pm.effort) == ("claude-code:sonnet", "medium")  # default_model, effort của provider
    assert (be.label, be.max_tokens, be.effort) == ("opencode-go:glm-5.3", 131072, None)
    monkeypatch.setenv("EFFORT_BACKEND", "low")
    assert target_for("backend", ps).effort == "low"
    monkeypatch.setenv("MODEL", "mock")                              # mock thắng mọi MODEL_<ROLE>
    assert "backend=mock" in describe(ps) and "opencode" not in describe(ps)


def test_target_errors(monkeypatch):
    ps = load_providers()
    monkeypatch.setenv("MODEL", "khong-co")
    with pytest.raises(ValueError, match="chưa khai báo"):
        target_for("pm", ps)
    for role in providers.ROLES:                                     # gõ sai MODEL vẫn phải lỗi khi mọi role
        monkeypatch.setenv(f"MODEL_{role.upper()}", "claude-code")   # đều có MODEL_<ROLE> hợp lệ
    with pytest.raises(ValueError, match="MODEL: provider"):
        target_for("pm", ps)
    assert all("LỖI(" in part for part in describe(ps).split(" · "))
    for role in providers.ROLES:
        monkeypatch.delenv(f"MODEL_{role.upper()}")
    monkeypatch.setenv("MODEL", "opencode-go")                       # provider không có default_model
    with pytest.raises(ValueError, match="thiếu model"):
        target_for("pm", ps)
    assert "LỖI(" in describe(ps)


def test_cli_model_overrides_every_role(monkeypatch):
    ps = load_providers()
    monkeypatch.setenv("MODEL", "claude-code")
    monkeypatch.setenv("MODEL_BACKEND", "opencode-go:glm-5.3")
    monkeypatch.setenv("MODEL_ALL", "ollama:qwen3:8b")             # --model: cả team, bỏ qua MODEL_<ROLE>
    assert {target_for(r, ps).label for r in providers.ROLES} == {"ollama:qwen3:8b"}
    monkeypatch.setenv("MODEL_ALL", "mock")
    assert not providers.uses_real_model(ps)
    monkeypatch.setenv("MODEL_ALL", "khong-co")
    with pytest.raises(ValueError, match="--model: provider"):
        target_for("backend", ps)
    monkeypatch.delenv("MODEL_ALL")
    assert providers.uses_real_model(ps)


def test_missing_keys_checked_before_run(monkeypatch):
    ps = load_providers()
    monkeypatch.setenv("MODEL", "claude-code")                   # claude-code không cần key
    monkeypatch.setenv("MODEL_TESTER", "openai:gpt-x")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert providers.missing_keys(ps) == ["tester: provider 'openai' cần OPENAI_API_KEY trong .env"]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert providers.missing_keys(ps) == []


def test_local_file_adds_and_overrides(tmp_path):
    base = tmp_path / "providers.toml"
    local = tmp_path / "providers.local.toml"
    base.write_text('[providers.a]\ntype = "openai-compatible"\nbase_url = "http://x/v1"\n', encoding="utf-8")
    local.write_text('[providers.a]\nread_timeout = 5\n[providers.b]\ntype = "anthropic"\n', encoding="utf-8")
    ps = load_providers((base, local))
    assert ps["a"].options == {"base_url": "http://x/v1", "read_timeout": 5} and ps["b"].type == "anthropic"
    local.write_text('[providers.c]\ntype = "grpc"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="type"):
        load_providers((base, local))


# ---------- adapter claude-code ----------

def _ok(structured):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "stop_reason": "end_turn", "structured_output": structured})


@pytest.fixture
def fake_claude(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    calls = []

    def install(*outputs):
        queue = list(outputs)

        def run(cmd, **kw):
            calls.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, 0, stdout=queue.pop(0), stderr="")
        monkeypatch.setattr(claude_code.subprocess, "run", run)
        return calls
    return install


def test_claude_code_command_and_subscription_auth(fake_claude):
    calls = fake_claude(_ok({"approved": True, "review_notes": "ok"}))
    out = claude_code.call(t("claude-code", "claude-opus-5-5", effort="medium"), "pm", "duyệt đi", PMReview)
    assert out == PMReview(approved=True, review_notes="ok")
    cmd, kw = calls[0]
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5" and cmd[cmd.index("--effort") + 1] == "medium"
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["title"] == "PMReview"
    assert cmd[cmd.index("--system-prompt-file") + 1].replace("\\", "/").endswith("skills/pm/SKILL.md")
    assert kw["input"] == "duyệt đi" and "ANTHROPIC_API_KEY" not in kw["env"]


def test_claude_code_retry_and_errors(fake_claude):
    calls = fake_claude(_ok({"approved": "?"}), _ok({"approved": False, "review_notes": "thiếu BR-03"}))
    assert claude_code.call(t("claude-code"), "pm", "x", PMReview).approved is False and len(calls) == 2
    assert "--effort" not in calls[0][0]                            # không có effort thì để mặc định của CLI
    fake_claude(json.dumps({"subtype": "success", "is_error": True, "result": "usage limit reached"}))
    with pytest.raises(RuntimeError, match="usage limit"):
        claude_code.call(t("claude-code"), "pm", "x", PMReview)


# ---------- adapter openai-compatible ----------

class FakeResponse:
    def __init__(self, chunks, status=200, text=""):
        self.status_code, self.text = status, text
        self._lines = [b"data: " + json.dumps(c).encode() for c in chunks] + [b"data: [DONE]"]

    def iter_lines(self):
        yield b": keep-alive"
        yield from self._lines

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def sse(content, finish="stop"):
    half = len(content) // 2
    return [{"choices": [{"delta": {"reasoning_content": "đang nghĩ..."}}]},
            {"choices": [{"delta": {"content": content[:half]}}]},
            {"choices": [{"delta": {"content": content[half:]}, "finish_reason": finish}]}]


@pytest.fixture
def fake_post(monkeypatch):
    calls = []

    def install(*responses):
        queue = list(responses)

        def post(url, **kw):
            calls.append((url, kw))
            return queue.pop(0)
        monkeypatch.setattr(openai_compat.requests, "post", post)
        return calls
    return install


def test_openai_compat_request_shape(fake_post, monkeypatch):
    monkeypatch.setenv("GO_KEY", "test-key")
    calls = fake_post(FakeResponse(sse('{"approved": true, "review_notes": "ok"}')))
    target = t(model="glm-5.3", name="opencode-go", base_url="https://h/v1/", api_key_env="GO_KEY",
               session_header="x-opencode-session", headers={"X-Extra": "1"})
    assert openai_compat.call(target, "pm", "duyệt", PMReview) == PMReview(approved=True, review_notes="ok")
    url, kw = calls[0]
    assert url == "https://h/v1/chat/completions"
    h = kw["headers"]
    assert h["Authorization"] == "Bearer test-key" and h["X-Extra"] == "1"
    assert h["User-Agent"] == openai_compat.USER_AGENT and h["x-opencode-session"].startswith("multi-agent-team-pm-")
    body = kw["json"]
    assert body["model"] == "glm-5.3" and body["stream"] is True and body["max_tokens"] == 64000
    assert body["response_format"]["json_schema"]["name"] == "PMReview" and "reasoning_effort" not in body


def test_openai_compat_local_server_options(fake_post):
    """Server local: không key, không session header, json_object, tên tham số riêng."""
    calls = fake_post(FakeResponse(sse("không phải JSON")),
                      FakeResponse(sse('```json\n{"approved": false, "review_notes": "x"}\n```')))
    target = t(model="qwen3:8b", effort="high", max_tokens=1000, base_url="http://localhost:11434/v1",
               response_format="json_object", effort_param="effort", max_tokens_param="max_completion_tokens")
    assert openai_compat.call(target, "tester", "x", PMReview).approved is False and len(calls) == 2
    kw = calls[0][1]
    assert "Authorization" not in kw["headers"] and not any("session" in k for k in kw["headers"])
    assert kw["json"]["response_format"] == {"type": "json_object"}
    assert kw["json"]["effort"] == "high" and kw["json"]["max_completion_tokens"] == 1000


def test_openai_compat_errors(fake_post, monkeypatch):
    monkeypatch.delenv("NO_SUCH_KEY", raising=False)
    with pytest.raises(RuntimeError, match="NO_SUCH_KEY"):
        openai_compat.call(t(base_url="http://h/v1", api_key_env="NO_SUCH_KEY"), "pm", "x", PMReview)
    fake_post(FakeResponse([], status=429, text="rate limited"))
    with pytest.raises(RuntimeError, match="429"):
        openai_compat.call(t(base_url="http://h/v1"), "pm", "x", PMReview)
    fake_post(FakeResponse(sse('{"approved": tr', finish="length")))
    with pytest.raises(RuntimeError, match="MAX_TOKENS_PM"):
        openai_compat.call(t(base_url="http://h/v1"), "pm", "x", PMReview)


# ---------- adapter anthropic ----------

class FakeAnthropic:
    def __init__(self, msg, sink):
        self._msg, self._sink = msg, sink
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self._sink.append(kwargs)
        msg = self._msg

        class Ctx:
            def __enter__(self):
                return SimpleNamespace(get_final_message=lambda: msg)

            def __exit__(self, *exc):
                return False
        return Ctx()


def test_anthropic_adapter_kwargs(monkeypatch):
    sent = []
    msg = SimpleNamespace(stop_reason="end_turn", parsed_output=PMReview(approved=True, review_notes="ok"), content=[])
    monkeypatch.setattr(anthropic_api, "_client", lambda target: FakeAnthropic(msg, sent))
    target = t("anthropic", "claude-opus-5-5", effort="medium", server_fallback=True)
    assert anthropic_api.call(target, "pm", "x", PMReview).approved is True
    kw = sent[0]
    assert kw["model"] == "claude-opus-5-5" and kw["output_format"] is PMReview
    assert kw["output_config"] == {"effort": "medium"} and kw["fallbacks"] == "default"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    # gateway tương thích Anthropic: không fallback, không effort khi không đặt
    anthropic_api.call(t("anthropic", "claude-haiku-5-5", prompt_cache=False), "pm", "x", PMReview)
    assert "fallbacks" not in sent[1] and "output_config" not in sent[1] and "cache_control" not in sent[1]["system"][0]
