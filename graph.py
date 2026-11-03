"""Định nghĩa graph LangGraph: node, edge, conditional edge (mục 3 và 5 trong spec)."""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.ba import ba
from agents.backend import backend
from agents.frontend import frontend
from agents.pm import pm_accept, pm_plan, pm_review
from agents.tester import tester
from state import MAX_ROUNDS, TeamState


def route_after_review(state: TeamState):
    if state.get("approved"):
        return ["backend", "frontend"]          # Dev chạy song song
    if state.get("review_round", 0) >= MAX_ROUNDS:
        return "pm_accept"                      # dừng, cần người xem lại
    return "ba"


def route_after_test(state: TeamState):
    bugs = state.get("bugs", [])
    if not bugs or state.get("iteration", 0) >= MAX_ROUNDS:
        return "pm_accept"
    owners = sorted({b["owner"] for b in bugs})  # chỉ Dev có bug mới phải sửa
    return owners


def build_graph(checkpointer=None):
    g = StateGraph(TeamState)
    for name, fn in [("pm_plan", pm_plan), ("ba", ba), ("pm_review", pm_review), ("backend", backend),
                     ("frontend", frontend), ("tester", tester), ("pm_accept", pm_accept)]:
        g.add_node(name, fn)
    g.add_edge(START, "pm_plan")
    g.add_edge("pm_plan", "ba")
    g.add_edge("ba", "pm_review")
    g.add_conditional_edges("pm_review", route_after_review, ["ba", "backend", "frontend", "pm_accept"])
    # BE và FE cùng chạy trong một bước thì tester chỉ chạy một lần sau khi cả hai xong
    g.add_edge("backend", "tester")
    g.add_edge("frontend", "tester")
    g.add_conditional_edges("tester", route_after_test, ["backend", "frontend", "pm_accept"])
    g.add_edge("pm_accept", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
