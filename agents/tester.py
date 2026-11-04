"""Tester: viết test case, chạy test, báo bug cho đúng người."""
from __future__ import annotations

from agents.common import ask, dump
from schemas import TesterOutput
from tools.file_tools import read_files, write_doc
from tools.plane_client import plane
from tools.runlog import log_step
from tools.test_runner import run_project_tests


def tester(state):
    tasks = dict(state["plane_tasks"])
    plane.move_task(tasks.get("TEST"), "In Progress")
    iteration = state.get("iteration", 0) + 1
    test_output = run_project_tests(state.get("tests"))
    prompt = (f"Vòng kiểm thử {iteration}.\n\nUser stories:\n{dump(state['user_stories'])}"
              f"\n\nAPI spec:\n{state.get('api_spec', '')}"
              f"\n\nCode backend:\n{read_files(state.get('backend_code', []))}"
              f"\n\nCode frontend:\n{read_files(state.get('frontend_code', []))}")
    if test_output:
        prompt += f"\n\nKết quả chạy test tự động:\n{test_output}"
    out = ask("tester", "tester", state, prompt, TesterOutput)
    bugs = [b.model_dump() for b in out.bugs]
    dismissed = state.get("dismissed") or {}
    bugs = [b for b in bugs if b["id"] not in dismissed]  # bug người dùng đã bỏ qua thì không mở lại
    report = out.report + (f"\n\n## Test tự động\n```\n{test_output}\n```" if test_output else "")
    write_doc(f"test_report_round{iteration}.md", report)
    write_doc("test_cases.md", "| id | story | rule | steps | expected | status |\n|---|---|---|---|---|---|\n" +
              "\n".join(f"| {t.id} | {t.story_id} | {t.rule} | {t.steps} | {t.expected} | {t.status} |"
                        for t in out.test_cases))
    if bugs:
        for b in bugs:
            tasks[f"{b['id']}-r{iteration}"] = plane.create_task(
                f"[Bug] {b['id']} {b['title']} ({b['ref']})", "BE" if b["owner"] == "backend" else "FE",
                "Todo", b["detail"])
            plane.move_task(tasks.get("BACKEND" if b["owner"] == "backend" else "FRONTEND"), "In Progress")
        plane.add_comment(tasks.get("TEST"), f"Vòng {iteration}: {len(bugs)} bug")
        summary = f"Vòng {iteration}: {len(out.test_cases)} TC, {len(bugs)} bug -> " + \
                  ", ".join(f"{b['id']}({b['ref']}, owner={b['owner']})" for b in bugs)
    else:
        plane.add_comment(tasks.get("TEST"), f"Vòng {iteration}: PASS {len(out.test_cases)} test case")
        plane.move_task(tasks.get("TEST"), "Done")
        summary = f"Vòng {iteration}: PASS {len(out.test_cases)} test case"
    entry = log_step(state["run_id"], "tester", summary)
    return {"test_cases": [t.model_dump() for t in out.test_cases], "test_report": report, "bugs": bugs,
            "iteration": iteration, "plane_tasks": tasks, "log": [entry],
            # Bản sửa bug sẽ qua Reviewer lại; mỗi vòng test có tối đa MAX_ROUNDS vòng review
            "code_review_round": 0}
