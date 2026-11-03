"""Backend Dev: thiết kế API và viết code server theo stack của dự án."""
from __future__ import annotations

from agents.common import ask, dump
from state import blocking_findings
from schemas import BackendOutput
from tools.file_tools import display, output_dir, read_files, write_doc, write_files
from tools.plane_client import plane
from tools.runlog import log_step


def backend(state):
    task = state["plane_tasks"].get("BACKEND")
    plane.move_task(task, "In Progress")
    my_bugs = [b for b in state.get("bugs", []) if b["owner"] == "backend"]
    my_findings = blocking_findings(state, "backend")
    prompt = f"User stories:\n{dump(state['user_stories'])}"
    if my_bugs or my_findings:
        prompt += (f"\n\nAPI spec hiện tại:\n{state.get('api_spec', '')}"
                   f"\n\nCode hiện tại:\n{read_files(state.get('backend_code', []))}"
                   + (f"\n\nBug Tester giao cho bạn:\n{dump(my_bugs)}" if my_bugs else "")
                   + (f"\n\nFinding Reviewer giao cho bạn:\n{dump(my_findings)}" if my_findings else ""))
    out = ask("backend", "backend", state, prompt, BackendOutput)
    written = write_files("backend", [f.model_dump() for f in out.files])
    write_doc("api_spec.md", out.api_spec)
    # Giữ danh sách file cũ, cộng thêm file mới (khi sửa bug chỉ trả file đã sửa)
    files = sorted(set(state.get("backend_code", [])) | set(written))
    plane.move_task(task, "In Review")
    if my_findings:
        action = f"sửa {len(my_findings)} finding review"
    elif my_bugs:
        action = f"sửa {len(my_bugs)} bug"
    else:
        action = "viết bản đầu"
    plane.add_comment(task, f"BE {action}, ghi {len(written)} file. {out.notes}")
    entry = log_step(state["run_id"], "backend", f"{action}, ghi {len(written)} file vào {display(output_dir() / 'backend')}")
    return {"api_spec": out.api_spec, "backend_code": files, "log": [entry]}
