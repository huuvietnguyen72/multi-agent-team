"""Reviewer: review code BE/FE theo 5 trục trước khi sang Tester."""
from __future__ import annotations

from agents.common import ask, dump
from schemas import ReviewOutput
from state import BLOCKING, MAX_ROUNDS
from tools.file_tools import read_files, write_doc
from tools.plane_client import plane
from tools.runlog import log_step


def reviewer(state):
    tasks = state["plane_tasks"]
    rnd = state.get("code_review_round", 0) + 1
    prompt = (f"Vòng review {rnd}.\n\nUser stories:\n{dump(state['user_stories'])}"
              f"\n\nAPI spec:\n{state.get('api_spec', '')}"
              f"\n\nCode backend:\n{read_files(state.get('backend_code', []))}"
              f"\n\nCode frontend:\n{read_files(state.get('frontend_code', []))}")
    if state.get("review_findings"):
        prompt += f"\n\nFinding vòng trước (kiểm tra đã sửa chưa):\n{dump(state['review_findings'])}"
    out = ask("reviewer", "reviewer", state, prompt, ReviewOutput)
    findings = [f.model_dump() for f in out.findings]
    dismissed = state.get("dismissed") or {}
    for f in findings:  # model nêu lại mục người dùng đã bỏ qua: giữ để xem, nhưng không chặn
        if f["id"] in dismissed:
            f["dismissed"], f["dismiss_reason"] = True, dismissed[f["id"]]
    blocking = [f for f in findings if f["severity"] in BLOCKING and not f.get("dismissed")]
    approved = not blocking  # không tin cờ của LLM nếu trái với danh sách finding

    lines = [f"# Code review vòng {rnd}\n", f"**{'DUYỆT' if approved else 'CẦN SỬA'}**: {out.summary}\n"]
    lines += [f"- `{f['severity']}` {f['id']} ({f['owner']}, {f['file']}): {f['detail']} → {f['suggestion']}"
              for f in findings]
    write_doc(f"code_review_test{state.get('iteration', 0) + 1}_round{rnd}.md", "\n".join(lines) + "\n")

    for owner, key in (("backend", "BACKEND"), ("frontend", "FRONTEND")):
        mine = [f for f in blocking if f["owner"] == owner]
        if mine:
            plane.move_task(tasks.get(key), "In Progress")
            plane.add_comment(tasks.get(key), "Reviewer yêu cầu sửa: " +
                              "; ".join(f"{f['id']} {f['detail']}" for f in mine))
        elif approved:
            plane.add_comment(tasks.get(key), f"Reviewer duyệt (vòng {rnd}). {out.summary}")

    nits = len(findings) - len(blocking)
    if approved:
        summary = f"Vòng {rnd}: DUYỆT, {nits} nit"
    else:
        summary = (f"Vòng {rnd}/{MAX_ROUNDS}: {len(blocking)} finding chặn -> " +
                   ", ".join(f"{f['id']}({f['severity']}, owner={f['owner']})" for f in blocking))
    entry = log_step(state["run_id"], "reviewer", summary)
    return {"review_approved": approved, "review_findings": findings, "review_summary": out.summary,
            "code_review_round": rnd, "log": [entry]}
