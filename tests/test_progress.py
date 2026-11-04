"""Sự kiện bước bên trong node (tools.runlog.progress) qua stream "custom" của LangGraph."""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from tools.runlog import progress


class S(TypedDict):
    log: Annotated[list, operator.add]


def _node(name):
    def run(state):
        progress("read")
        progress("model", model="mock")
        progress("write")
        return {"log": [name]}
    return run


def _graph():
    g = StateGraph(S)
    for n in ("plan", "backend", "frontend"):
        g.add_node(n, _node(n))
    g.add_edge(START, "plan")
    g.add_edge("plan", "backend")
    g.add_edge("plan", "frontend")
    g.add_edge("backend", END)
    g.add_edge("frontend", END)
    return g.compile()


def test_progress_outside_graph_is_noop():
    progress("read")  # không lỗi, không làm gì


def test_progress_events_carry_node():
    seen = []
    for mode, chunk in _graph().stream({"log": []}, stream_mode=["tasks", "updates", "custom"]):
        if mode == "tasks" and "input" in chunk:
            seen.append(("start", chunk["name"]))
        elif mode == "updates":
            seen += [("done", n) for n in chunk]
        elif mode == "custom":
            seen.append((chunk["phase"], chunk["node"]))
    for node in ("plan", "backend", "frontend"):
        start, done = seen.index(("start", node)), seen.index(("done", node))
        phases = [p for p, n in seen[start + 1:done] if n == node]
        assert phases == ["read", "model", "write"], (node, seen)


def test_invoke_ignores_progress():
    assert sorted(_graph().invoke({"log": []})["log"]) == ["backend", "frontend", "plan"]
