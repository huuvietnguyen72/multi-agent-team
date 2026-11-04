"""Chuẩn bị lượt chạy dùng chung cho main.py và giao diện."""
import pytest

from agents.providers import ROLES
from tests.test_providers import ROLE_VARS
from tools.run import format_models, prepare_run


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ROLE_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)  # prepare_run đặt biến này; monkeypatch trả lại sau test


def test_prepare_run_mock_is_ready(tmp_path):
    setup = prepare_run("example", mock=True, output_dir=tmp_path)
    assert setup.problems == []
    assert setup.models == {r: "mock" for r in ROLES}
    assert setup.real_model is False
    assert setup.state["project"] == "example"
    assert setup.state["models"] == setup.models


def test_prepare_run_names_bad_role(tmp_path):
    models = {r: "mock" for r in ROLES} | {"reviewer": "nope:x"}
    setup = prepare_run("example", models=models, output_dir=tmp_path)
    assert len(setup.problems) == 1 and setup.problems[0].startswith("reviewer:")


def test_prepare_run_rejects_escalate_reviewer(monkeypatch, tmp_path):
    monkeypatch.setenv("ESCALATE_REVIEWER", "claude-code:opus")
    setup = prepare_run("example", output_dir=tmp_path)
    assert any("ESCALATE_REVIEWER" in p for p in setup.problems)


def test_setup_copies_model_maps(tmp_path):
    models = {r: "mock" for r in ROLES}
    setup = prepare_run("example", models=models, output_dir=tmp_path)
    models["pm"] = "claude-code:opus"
    assert setup.state["models"]["pm"] == "mock"


def test_format_models_shows_escalation(tmp_path):
    setup = prepare_run("example", models={r: "claude-code:sonnet" for r in ROLES},
                        escalate={"backend": "claude-code:opus"}, output_dir=tmp_path)
    assert "backend=claude-code:sonnet (vòng cuối: claude-code:opus)" in format_models(setup)
    assert setup.real_model is True


def test_prepare_run_unknown_project(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_run("khong-co-du-an-nay", output_dir=tmp_path)


def test_format_models_code_quotes_names(tmp_path):
    """Trong markdown của Chainlit, ':sonnet' bị đọc là directive và mất chữ; bọc code thì giữ nguyên."""
    setup = prepare_run("example", models={"backend": "opencode-go:glm-5.3"}, escalate={}, mock=False,
                        run_id="t", output_dir=tmp_path)
    assert "backend=`opencode-go:glm-5.3`" in format_models(setup, code=True)


def test_format_models_whole_team(tmp_path):
    setup = prepare_run("example", mock=True, run_id="t", output_dir=tmp_path)
    assert format_models(setup) == "cả team=mock"


def test_archive_output_moves_previous_run(tmp_path):
    from tools.run import HISTORY_KEEP, archive_output, output_run_id
    out = tmp_path / "output"
    assert archive_output(out, "r0") is None                 # chưa có gì
    for i in range(HISTORY_KEEP + 2):
        (out / "docs").mkdir(parents=True, exist_ok=True)
        (out / "docs" / "a.md").write_text(str(i))
        moved = archive_output(out, f"r{i + 1:02d}")
        previous = "r0" if i == 0 else f"r{i:02d}"             # thư mục mang mã của lượt đã ghi đầu ra đó
        assert moved.name == previous and (moved / "docs" / "a.md").read_text() == str(i)
        assert out.is_dir() and not any(out.iterdir())
    assert len(list((tmp_path / "output_history").iterdir())) == HISTORY_KEEP
    assert output_run_id(out) == f"r{HISTORY_KEEP + 2:02d}"
