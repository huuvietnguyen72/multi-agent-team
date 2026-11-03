"""Kiểm tra luật định tuyến (mục 5) và một lần chạy đủ graph với agent giả."""
from graph import build_graph, route_after_review, route_after_test


def test_review_routes():
    assert route_after_review({"approved": True}) == ["backend", "frontend"]
    assert route_after_review({"approved": False, "review_round": 1}) == "ba"
    assert route_after_review({"approved": False, "review_round": 3}) == "pm_accept"


def test_test_routes():
    assert route_after_test({"bugs": [], "iteration": 1}) == "pm_accept"
    assert route_after_test({"bugs": [{"owner": "backend"}], "iteration": 1}) == ["backend"]
    both = [{"owner": "frontend"}, {"owner": "backend"}]
    assert route_after_test({"bugs": both, "iteration": 2}) == ["backend", "frontend"]
    assert route_after_test({"bugs": both, "iteration": 3}) == "pm_accept"


def test_full_mock_run(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "mock")
    app = build_graph()
    final = app.invoke({"run_id": "pytest", "requirements": "x", "log": []},
                       config={"configurable": {"thread_id": "pytest"}})
    nodes = [e["node"] for e in final["log"]]
    assert nodes[:5] == ["pm_plan", "ba", "pm_review", "ba", "pm_review"]
    assert nodes.count("tester") == 2 and nodes[-1] == "pm_accept"
    assert final["final_status"] == "ACCEPTED"
