"""Frontend Dev: viết giao diện gọi API của Backend, theo stack của dự án."""
from __future__ import annotations

from agents.common import ask, dump
from state import blocking_findings
from schemas import FrontendOutput
from tools.file_tools import display, output_dir, read_files, write_files
from tools.plane_client import plane
from tools.runlog import log_step


def frontend(state):
    task = state["plane_tasks"].get("FRONTEND")
    plane.move_task(task, "In Progress")
    my_bugs = [b for b in state.get("bugs", []) if b["owner"] == "frontend"]
    my_findings = blocking_findings(state, "frontend")
    prompt = f"User stories:\n{dump(state['user_stories'])}"
    if state.get("api_spec"):
        prompt += f"\n\nAPI spec của Backend:\n{state['api_spec']}"
    if my_bugs or my_findings:
        prompt += (f"\n\nCode hiện tại:\n{read_files(state.get('frontend_code', []))}"
                   + (f"\n\nBug Tester giao cho bạn:\n{dump(my_bugs)}" if my_bugs else "")
                   + (f"\n\nFinding Reviewer giao cho bạn:\n{dump(my_findings)}" if my_findings else ""))
    out = ask("frontend", "frontend", state, prompt, FrontendOutput)
    written = write_files("frontend", [f.model_dump() for f in out.files])
    files = sorted(set(state.get("frontend_code", [])) | set(written))
    plane.move_task(task, "In Review")
    if my_findings:
        action = f"sửa {len(my_findings)} finding review"
    elif my_bugs:
        action = f"sửa {len(my_bugs)} bug"
    else:
        action = "viết bản đầu"
    plane.add_comment(task, f"FE {action}, ghi {len(written)} file. {out.notes}")
    entry = log_step(state["run_id"], "frontend", f"{action}, ghi {len(written)} file vào {display(output_dir() / 'frontend')}")
    return {"frontend_code": files, "log": [entry]}
