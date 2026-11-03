"""PM: lập kế hoạch (pm_plan), duyệt phân tích (pm_review), nghiệm thu (pm_accept)."""
from __future__ import annotations

from agents.common import ask, dump
from schemas import PMAccept, PMPlan, PMReview
from state import MAX_ROUNDS
from tools.file_tools import write_doc
from tools.plane_client import plane
from tools.runlog import log_step


def pm_plan(state):
    prompt = f"Lập kế hoạch dự án cho requirements sau:\n\n{state['requirements']}"
    out = ask("pm", "pm_plan", state, prompt, PMPlan)
    tasks = {}
    for t in out.tasks:
        st = "Todo" if t.role == "BA" else "Backlog"
        tasks[t.key] = plane.create_task(t.title, t.role, st, t.description)
    entry = log_step(state["run_id"], "pm_plan", f"Tạo {len(out.tasks)} task: {out.summary}")
    return {"plan": [t.model_dump() for t in out.tasks], "plane_tasks": tasks,
            "review_round": 0, "iteration": 0, "bugs": [], "log": [entry]}


def pm_review(state):
    prompt = (f"Requirements:\n{state['requirements']}\n\nUser stories của BA:\n{dump(state['user_stories'])}\n\n"
              "Duyệt theo checklist trong skill.")
    out = ask("pm", "pm_review", state, prompt, PMReview)
    tasks = state["plane_tasks"]
    analysis = tasks.get("ANALYSIS")
    update = {"approved": out.approved, "review_notes": "" if out.approved else out.review_notes}
    if out.approved:
        plane.move_task(analysis, "Done")
        plane.add_comment(analysis, f"PM duyệt: {out.review_notes}")
        new_tasks = dict(tasks)
        for us in state["user_stories"]:
            for label, parent in (("BE", "BACKEND"), ("FE", "FRONTEND")):
                new_tasks[f"{us['id']}-{label}"] = plane.create_task(
                    f"{us['id']} {us['title']} ({label})", label, "Todo", parent_id=tasks.get(parent))
        update["plane_tasks"] = new_tasks
        summary = f"DUYỆT: {out.review_notes}"
    else:
        update["review_round"] = state.get("review_round", 0) + 1
        plane.move_task(analysis, "In Progress")
        plane.add_comment(analysis, f"PM trả lại (vòng {update['review_round']}): {out.review_notes}")
        summary = f"TRẢ LẠI BA (vòng {update['review_round']}/{MAX_ROUNDS}): {out.review_notes}"
    update["log"] = [log_step(state["run_id"], "pm_review", summary)]
    return update


def pm_accept(state):
    prompt = (f"Tổng kết dự án.\nSố vòng review: {state.get('review_round', 0)}\n"
              f"Duyệt phân tích: {state.get('approved')}\nSố vòng test: {state.get('iteration', 0)}\n"
              f"Bug tồn đọng: {dump(state.get('bugs', []))}\nTest report:\n{state.get('test_report', '')}")
    out = ask("pm", "pm_accept", state, prompt, PMAccept)
    tasks = state["plane_tasks"]
    if out.final_status == "ACCEPTED":
        for key in ("BACKEND", "FRONTEND", "TEST"):
            plane.move_task(tasks.get(key), "Done")
    for key in ("ANALYSIS", "BACKEND", "FRONTEND", "TEST"):
        plane.add_comment(tasks.get(key), f"Nghiệm thu: {out.final_status}. {out.summary}")
    write_doc("final_report.md", f"# Nghiệm thu\n\n**{out.final_status}**\n\n{out.summary}\n")
    entry = log_step(state["run_id"], "pm_accept", f"{out.final_status}: {out.summary}")
    return {"final_status": out.final_status, "log": [entry]}
