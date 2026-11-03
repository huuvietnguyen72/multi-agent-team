"""BA: phân tích requirements thành user stories."""
from __future__ import annotations

from agents.common import ask, dump
from schemas import BAOutput
from tools.file_tools import write_doc
from tools.plane_client import plane
from tools.runlog import log_step


def ba(state):
    task = state["plane_tasks"].get("ANALYSIS")
    plane.move_task(task, "In Progress")
    prompt = f"Requirements:\n{state['requirements']}"
    if state.get("review_notes"):
        prompt += (f"\n\nBản trước của bạn:\n{dump(state.get('user_stories', []))}"
                   f"\n\nPM yêu cầu sửa:\n{state['review_notes']}")
    out = ask("ba", "ba", state, prompt, BAOutput)
    stories = [s.model_dump() for s in out.user_stories]
    path = write_doc("user_stories.md", _to_markdown(stories))
    plane.move_task(task, "In Review")
    plane.add_comment(task, f"BA nộp {len(stories)} user stories: {path}")
    entry = log_step(state["run_id"], "ba", f"Viết {len(stories)} user stories -> {path}")
    return {"user_stories": stories, "log": [entry]}


def _to_markdown(stories: list[dict]) -> str:
    lines = ["# User stories\n"]
    for s in stories:
        lines.append(f"## {s['id']} {s['title']}\n")
        lines.append(f"Là **{s['as_a']}**, tôi muốn **{s['i_want']}** để **{s['so_that']}**.\n")
        lines.append(f"Chức năng: {', '.join(s['features'])} · Business rules: {', '.join(s['business_rules']) or '-'}\n")
        lines += [f"- {ac}" for ac in s["acceptance_criteria"]]
        lines.append("")
    return "\n".join(lines)
