"""Các lượt làm việc của từng role cho khung "Chi tiết" (FR-13 đến FR-15): việc được giao, các bước
bên trong lượt, model, thời gian, và phần sửa (diff) của từng file. Không phụ thuộc Chainlit."""
from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from state import MAX_ROUNDS, blocking_findings
from ui.view import AUTHORS, STEPS, changed_files, files_for

MAX_DIFF_LINES = 400
PHASES = ("start", "read", "model", "write", "done")   # 5 bước của FR-14
PHASE_LABELS = {"start": "Nhận việc", "read": "Đọc code", "model": "Chờ model trả lời", "write": "Ghi tệp",
                "done": "Xong"}
ROLE_ORDER = ("PM", "BA", "Backend", "Frontend", "Reviewer", "Tester")
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class DiffLine:
    kind: str              # "hunk" | "ctx" | "add" | "del"
    old: int | None        # số dòng cũ
    new: int | None        # số dòng mới
    text: str


@dataclass
class FileChange:
    path: str              # tương đối với output, ví dụ backend/src/.../BorrowService.java
    added: int
    removed: int
    lines: list[DiffLine]
    truncated: bool        # True khi dài quá MAX_DIFF_LINES
    note: str = ""         # lý do không có diff
    new_file: bool = False


@dataclass
class Turn:
    role: str              # tác giả: PM, BA, Backend, Frontend, Reviewer, Tester
    n: int                 # lượt thứ mấy của role, từ 1
    node: str
    task: str              # "Bản đầu", "Sửa CR-01", "Sửa BUG-02 (BR-03)", ...
    found_by: str | None   # "Reviewer vòng 1/3", "Tester vòng 2/3"
    status: str            # "running" | "done" | "failed"
    phase: str             # một giá trị trong PHASES
    started: float
    seconds: float | None = None
    chars: int | None = None
    model: str | None = None
    escalated_from: str | None = None
    files: list[FileChange] = field(default_factory=list)
    seen: list[str] = field(default_factory=lambda: ["start"])  # các bước đã đi qua; bước bỏ qua không hiện


def diff_file(path: str, old: str | None, new: str | None) -> FileChange:
    """Diff kiểu unified, 3 dòng ngữ cảnh. old None: file mới. new None: không đọc được nội dung."""
    if new is None:
        return FileChange(path, 0, 0, [], False, note="file nhị phân hoặc lớn hơn 1 MB")
    lines: list[DiffLine] = []
    added = removed = 0
    o = n = 0
    raw = difflib.unified_diff((old or "").splitlines(), new.splitlines(), lineterm="", n=3)
    for line in raw:
        if line.startswith(("---", "+++")) and not lines:
            continue
        if m := _HUNK.match(line):
            o, n = int(m.group(1)), int(m.group(2))
            o, n = max(o, 1), max(n, 1)
            lines.append(DiffLine("hunk", None, None, line))
        elif line.startswith("+"):
            lines.append(DiffLine("add", None, n, line[1:]))
            n += 1
            added += 1
        elif line.startswith("-"):
            lines.append(DiffLine("del", o, None, line[1:]))
            o += 1
            removed += 1
        else:
            lines.append(DiffLine("ctx", o, n, line[1:] if line.startswith(" ") else line))
            o += 1
            n += 1
    truncated = len(lines) > MAX_DIFF_LINES
    return FileChange(path, added, removed, lines[:MAX_DIFF_LINES], truncated, new_file=old is None)


def file_changes(node: str, before: dict, after: dict, output_dir: Path) -> list[FileChange]:
    """Phần sửa của một node, từ hai ảnh chụp ui.view.snapshot() lúc node bắt đầu và lúc xong."""
    root = Path(output_dir)
    out = []
    for p in files_for(node, changed_files(before, after), root):
        rel = p.relative_to(root).as_posix()
        new = after[p][2]
        if p not in before:
            out.append(diff_file(rel, None, new))
        elif before[p][2] is None:
            out.append(diff_file(rel, "", None))
        elif before[p][2] != new:  # ghi lại y nguyên thì không tính là sửa
            out.append(diff_file(rel, before[p][2], new))
    return out


def turn_task(node: str, state: dict) -> tuple[str, str | None]:
    """(việc được giao, ai tìm thấy lỗi) đọc từ state lúc node bắt đầu."""
    review, iteration = state.get("code_review_round", 0), state.get("iteration", 0)
    if node in ("backend", "frontend"):
        findings = blocking_findings(state, node)
        if review > 0 and findings:
            return "Sửa " + ", ".join(f["id"] for f in findings), f"Reviewer vòng {review}/{MAX_ROUNDS}"
        bugs = [b for b in state.get("bugs", []) if b.get("owner") == node]
        if iteration > 0 and bugs:
            return ("Sửa " + ", ".join(f"{b['id']} ({b['ref']})" if b.get("ref") else b["id"] for b in bugs),
                    f"Tester vòng {iteration}/{MAX_ROUNDS}")
        return "Bản đầu", None
    if node == "ba":
        rnd = state.get("review_round", 0)
        return ("Sửa theo góp ý của PM", f"PM vòng {rnd}/{MAX_ROUNDS}") if rnd > 0 else ("Viết user story", None)
    if node == "reviewer":
        return f"Review code vòng {review + 1}/{MAX_ROUNDS}", None
    if node == "tester":
        return f"Kiểm thử vòng {iteration + 1}/{MAX_ROUNDS}", None
    return dict(STEPS).get(node, node), None


class Turns:
    """Lượt của 6 role trong một phiên giao diện."""

    def __init__(self) -> None:
        self.all: list[Turn] = []
        self.current: dict[str, Turn] = {}

    def start(self, node: str, state: dict, now: float) -> Turn:
        role = AUTHORS.get(node, node)
        task, found_by = turn_task(node, state or {})
        turn = Turn(role=role, n=sum(t.role == role for t in self.all) + 1, node=node, task=task,
                    found_by=found_by, status="running", phase="start", started=now)
        self.all.append(turn)
        self.current[node] = turn
        return turn

    def progress(self, node: str, data: dict) -> Turn | None:
        turn = self.current.get(node)
        if turn is None:
            return None
        phase = data.get("phase")
        if phase == "stream":
            turn.chars = data.get("chars")
        elif phase in PHASES and PHASES.index(phase) > PHASES.index(turn.phase):
            turn.phase = phase
            turn.seen.append(phase)
        if data.get("model"):
            turn.model = data["model"]
        if data.get("escalated_from"):
            turn.escalated_from = data["escalated_from"]
        return turn

    def finish(self, node: str, files: list[FileChange], log_data: dict, now: float) -> Turn | None:
        turn = self.current.pop(node, None)
        if turn is None:
            return None
        turn.status, turn.phase, turn.files = "done", "done", files
        turn.seen.append("done")
        turn.seconds = round(now - turn.started, 1)
        turn.model = log_data.get("model") or turn.model
        turn.escalated_from = log_data.get("escalated_from") or turn.escalated_from
        return turn

    def fail(self, node: str, now: float) -> Turn | None:
        turn = self.current.pop(node, None)
        if turn is not None:
            turn.status = "failed"
            turn.seconds = round(now - turn.started, 1)
        return turn

    def of(self, role: str) -> list[Turn]:
        return [t for t in reversed(self.all) if t.role == role]

    def props(self, role: str, now: float) -> dict:
        """Props cho public/elements/RoleDetail.jsx."""
        turns = []
        for t in self.of(role):
            d = asdict(t)
            d["elapsed"] = int(now - t.started) if t.status == "running" else None
            d["added"] = sum(f.added for f in t.files)
            d["removed"] = sum(f.removed for f in t.files)
            turns.append(d)
        status = {r: ("running" if any(t.status == "running" for t in self.of(r)) else "done" if self.of(r) else "idle")
                  for r in ROLE_ORDER}
        return {"role": role, "roles": list(ROLE_ORDER), "role_status": status, "turns": turns,
                "phases": [[p, PHASE_LABELS[p]] for p in PHASES]}
