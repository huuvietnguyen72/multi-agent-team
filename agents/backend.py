"""Backend Dev: thiết kế API và viết code Spring Boot."""
from __future__ import annotations

from agents.common import ask, dump
from schemas import BackendOutput
from tools.file_tools import read_files, write_doc, write_files
from tools.plane_client import plane
from tools.runlog import log_step


def backend(state):
    task = state["plane_tasks"].get("BACKEND")
    plane.move_task(task, "In Progress")
    my_bugs = [b for b in state.get("bugs", []) if b["owner"] == "backend"]
    prompt = f"User stories:\n{dump(state['user_stories'])}"
    if my_bugs:
        prompt += (f"\n\nAPI spec hiện tại:\n{state.get('api_spec', '')}"
                   f"\n\nCode hiện tại:\n{read_files(state.get('backend_code', []))}"
                   f"\n\nBug Tester giao cho bạn:\n{dump(my_bugs)}")
    out = ask("backend", "backend", state, prompt, BackendOutput)
    written = write_files("backend", [f.model_dump() for f in out.files])
    write_doc("api_spec.md", out.api_spec)
    # Giữ danh sách file cũ, cộng thêm file mới (khi sửa bug chỉ trả file đã sửa)
    files = sorted(set(state.get("backend_code", [])) | set(written))
    plane.move_task(task, "In Review")
    action = f"sửa {len(my_bugs)} bug" if my_bugs else "viết bản đầu"
    plane.add_comment(task, f"BE {action}, ghi {len(written)} file. {out.notes}")
    entry = log_step(state["run_id"], "backend", f"{action}, ghi {len(written)} file vào output/backend")
    return {"api_spec": out.api_spec, "backend_code": files, "log": [entry]}
