"""Kiểm tra luật định tuyến (mục 5) và một lần chạy đủ graph với agent giả."""
from agents.skills import load_skill
from graph import build_graph, route_after_code_review, route_after_review, route_after_test


def test_review_routes():
    assert route_after_review({"approved": True}) == ["backend", "frontend"]
    assert route_after_review({"approved": False, "review_round": 1}) == "ba"
    assert route_after_review({"approved": False, "review_round": 3}) == "pm_accept"


def test_code_review_routes():
    fe_req = {"severity": "required", "owner": "frontend"}
    be_crit = {"severity": "critical", "owner": "backend"}
    nit = {"severity": "nit", "owner": "backend"}
    assert route_after_code_review({"review_findings": [], "code_review_round": 1}) == "tester"
    assert route_after_code_review({"review_findings": [nit], "code_review_round": 1}) == "tester"
    assert route_after_code_review({"review_findings": [fe_req, nit], "code_review_round": 1}) == ["frontend"]
    assert route_after_code_review({"review_findings": [fe_req, be_crit], "code_review_round": 2}) == \
        ["backend", "frontend"]
    assert route_after_code_review({"review_findings": [fe_req], "code_review_round": 3}) == "tester"


def test_test_routes():
    assert route_after_test({"bugs": [], "iteration": 1}) == "pm_accept"
    assert route_after_test({"bugs": [{"owner": "backend"}], "iteration": 1}) == ["backend"]
    both = [{"owner": "frontend"}, {"owner": "backend"}]
    assert route_after_test({"bugs": both, "iteration": 2}) == ["backend", "frontend"]
    assert route_after_test({"bugs": both, "iteration": 3}) == "pm_accept"


def test_skills_have_frontmatter_and_sections():
    from pathlib import Path
    for role in ["pm", "ba", "backend", "frontend", "reviewer", "tester"]:
        raw = (Path(__file__).resolve().parent.parent / "skills" / role / "SKILL.md").read_text(encoding="utf-8")
        assert raw.startswith(f"---\nname: {role}\ndescription: "), role
        body = load_skill(role)
        assert not body.startswith("---") and "description:" not in body.split("\n")[0]
        for section in ["## Overview", "## When to Use", "## Process", "## Red Flags", "## Verification"]:
            assert section in body, (role, section)


def test_full_mock_run(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL", "mock")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))  # không ghi đè output của dự án nào
    app = build_graph()
    final = app.invoke({"run_id": "pytest", "requirements": "x", "log": []},
                       config={"configurable": {"thread_id": "pytest"}})
    nodes = [e["node"] for e in final["log"]]
    assert nodes[:5] == ["pm_plan", "ba", "pm_review", "ba", "pm_review"]
    assert sorted(nodes[5:7]) == ["backend", "frontend"]
    assert nodes[7:] == ["reviewer", "frontend", "reviewer", "tester", "backend", "reviewer", "tester",
                         "pm_accept"]
    assert final["final_status"] == "ACCEPTED"
    assert (tmp_path / "docs" / "final_report.md").is_file() and (tmp_path / "backend").is_dir()
