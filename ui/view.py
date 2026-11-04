"""Nội dung hiển thị của giao diện, viết thành hàm thuần để test không cần Chainlit:
tin nhắn của từng role, bảng tiến độ, file đính kèm, tin tổng kết, che API key."""
from __future__ import annotations

import os
from pathlib import Path

from state import BLOCKING, MAX_ROUNDS

STEPS: tuple[tuple[str, str], ...] = (
    ("pm_plan", "Lập kế hoạch"), ("ba", "Viết user story"), ("pm_review", "PM duyệt"),
    ("backend", "Backend"), ("frontend", "Frontend"), ("reviewer", "Review code"),
    ("tester", "Kiểm thử"), ("pm_accept", "Nghiệm thu"))
AUTHORS: dict[str, str] = {"pm_plan": "PM", "pm_review": "PM", "pm_accept": "PM", "ba": "BA",
                           "backend": "Backend", "frontend": "Frontend", "reviewer": "Reviewer", "tester": "Tester"}
OWNERS = {"backend": "Backend", "frontend": "Frontend"}
LANGUAGES = {".java": "java", ".js": "javascript", ".html": "html", ".css": "css", ".md": "markdown",
             ".xml": "xml", ".sql": "sql", ".json": "json", ".py": "python"}


class Progress:
    """Trạng thái 8 dòng của bảng tiến độ: "ready" | "running" | "done" | "failed"."""

    def __init__(self) -> None:
        self.status = {node: "ready" for node, _ in STEPS}
        self.review_round = 0  # code_review_round gần nhất (Tester đặt lại về 0)
        self.shown_review = 0  # vòng của lần review gần nhất, hiện khi dòng đã xong
        self.iteration = 0     # số vòng test gần nhất

    def start(self, node: str) -> None:
        self.status[node] = "running"

    def finish(self, node: str, update: dict) -> None:
        self.status[node] = "done"
        if node == "reviewer":
            self.review_round = update.get("code_review_round", self.review_round + 1)
            self.shown_review = self.review_round
        elif node == "tester":
            self.iteration = update.get("iteration", self.iteration + 1)
            self.review_round = update.get("code_review_round", 0)

    def fail(self, node: str) -> None:
        self.status[node] = "failed"

    def title(self, node: str) -> str:
        label = dict(STEPS)[node]
        st = self.status[node]
        if node == "reviewer" and st != "ready":
            k = self.review_round + 1 if st == "running" else self.shown_review
            return f"{label} (vòng {k}/{MAX_ROUNDS})"
        if node == "tester" and st != "ready":
            k = self.iteration + 1 if st == "running" else self.iteration
            return f"{label} (vòng {k}/{MAX_ROUNDS})"
        return label

    def rows(self) -> list[tuple[str, str]]:
        return [(self.title(node), self.status[node]) for node, _ in STEPS]


def _last_log(update: dict) -> dict:
    log = update.get("log") or []
    return log[-1] if log else {}


def _footer(data: dict) -> str:
    model = data.get("model", "?")
    seconds = data.get("seconds")
    line = f"_model:_ `{model}`" + (f" _· {seconds:g} giây_" if seconds is not None else "")
    if data.get("escalated_from"):
        line = (f"Đổi từ `{data['escalated_from']}` sang `{model}` vì đây là vòng sửa cuối.\n\n" + line)
    return line


def _body(node: str, update: dict, summary: str) -> str:
    if node == "pm_plan":
        rows = "\n".join(f"| {t.get('key')} | {t.get('role')} | {t.get('title')} |" for t in update.get("plan", []))
        text = summary.split(": ", 1)[-1] if ": " in summary else summary
        return f"**Lập kế hoạch.** {text}\n\n| Task | Role | Tiêu đề |\n|---|---|---|\n{rows}"
    if node == "ba":
        stories = update.get("user_stories", [])
        items = "\n".join(f"- **{us.get('id')}** {us.get('title')}" for us in stories)
        return f"Viết {len(stories)} user story:\n\n{items}"
    if node == "pm_review":
        verdict, _, notes = summary.partition(": ")
        return f"**{verdict}**: {notes}" if notes else f"**{verdict}**"
    if node in ("backend", "frontend"):
        return summary[:1].upper() + summary[1:]
    if node == "reviewer":
        findings = update.get("review_findings", [])
        blocking = [f for f in findings if f.get("severity") in BLOCKING]
        nits = len(findings) - len(blocking)
        if not blocking:
            return f"**DUYỆT**, {nits} nit."
        items = "\n".join(f"- **{f.get('id')}** ({f.get('severity')}, giao {OWNERS.get(f.get('owner'), f.get('owner'))}, "
                          f"`{f.get('file')}`): {f.get('detail')}" for f in blocking)
        rnd = update.get("code_review_round", "?")
        return f"**YÊU CẦU SỬA** (vòng {rnd}/{MAX_ROUNDS}), {len(blocking)} finding chặn, {nits} nit:\n\n{items}"
    if node == "tester":
        cases, bugs = update.get("test_cases", []), update.get("bugs", [])
        rnd = update.get("iteration", "?")
        if not bugs:
            return f"**ĐẠT** (vòng {rnd}/{MAX_ROUNDS}): {len(cases)} test case đều PASS."
        items = "\n".join(f"- **{b.get('id')}** ({b.get('ref')}, giao {OWNERS.get(b.get('owner'), b.get('owner'))}): "
                          f"{b.get('title')}" for b in bugs)
        return f"**CÓ LỖI** (vòng {rnd}/{MAX_ROUNDS}): {len(cases)} test case, {len(bugs)} bug:\n\n{items}"
    if node == "pm_accept":
        verdict, _, notes = summary.partition(": ")
        return f"**{verdict}**: {notes}" if notes else f"**{verdict}**"
    return summary


def message_for(node: str, update: dict) -> str:
    """Markdown của tin nhắn cho một node vừa xong (FR-06), dòng cuối là model và thời gian."""
    entry = _last_log(update)
    return _body(node, update, entry.get("summary", "")) + "\n\n" + _footer(entry.get("data") or {})


MAX_TEXT_BYTES = 1_000_000


def snapshot(output_dir: Path) -> dict[Path, tuple[int, int, str | None]]:
    """file -> (mtime_ns, size, nội dung UTF-8). Nội dung là None khi file nhị phân hoặc lớn hơn
    MAX_TEXT_BYTES. Thư mục chưa có thì trả {}."""
    root = Path(output_dir)
    if not root.is_dir():
        return {}
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            text = None
            if st.st_size <= MAX_TEXT_BYTES:
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    text = None
            out[p] = (st.st_mtime_ns, st.st_size, text)
    return out


def changed_files(before: dict, after: dict) -> list[Path]:
    """File mới, hoặc file có (mtime_ns, size) khác lần chụp trước."""
    return sorted(p for p, sig in after.items() if p not in before or before[p][:2] != sig[:2])


def files_for(node: str, changed: list[Path], output_dir: Path) -> list[Path]:
    """Phần file của một node, để hai node chạy song song không nhận file của nhau."""
    root = Path(output_dir)
    out = []
    for p in changed:
        try:
            rel = Path(p).relative_to(root)
        except ValueError:
            continue
        top = rel.parts[0] if rel.parts else ""
        is_spec = rel == Path("docs") / "api_spec.md"
        if node == "backend":
            ok = top == "backend" or is_spec
        elif node == "frontend":
            ok = top == "frontend"
        else:
            ok = top == "docs" and not is_spec
        if ok:
            out.append(Path(p))
    return out


def language_for(path: Path) -> str | None:
    return LANGUAGES.get(Path(path).suffix.lower())


def summary_text(final: dict, setup, seconds: float) -> str:
    """Tin tổng kết sau nghiệm thu (FR-09)."""
    from tools.file_tools import display
    from tools.run import format_models
    log = final.get("log") or []
    status = final.get("final_status") or "chưa đạt"
    minutes, secs = divmod(int(round(seconds)), 60)
    changes = [f"- {e['node']}: `{e['data']['escalated_from']}` → `{e['data'].get('model')}`"
               for e in log if (e.get("data") or {}).get("escalated_from")]
    lines = [
        f"**Kết quả: {status}**",
        "",
        f"- {len(log)} bước, {final.get('review_round', 0)} lần trả BA, {final.get('iteration', 0)} vòng test",
        f"- Thời gian: {minutes} phút {secs:02d} giây",
        f"- Model: {format_models(setup)}",
    ]
    if changes:
        lines += ["- Đổi model ở vòng sửa cuối:"] + ["  " + c for c in changes]
    lines += [f"- Output: `{display(Path(os.getenv('OUTPUT_DIR') or setup.project.output_dir))}`",
              f"- Log: `runs/{setup.run_id}.jsonl`"]
    return "\n".join(lines)


def secret_values(providers: dict) -> list[str]:
    """Giá trị của mọi biến API key đang có (api_key_env của provider, cùng PLANE_API_KEY)."""
    names = {p.options.get("api_key_env") for p in providers.values()} | {"PLANE_API_KEY"}
    return [v for n in names if n and (v := os.getenv(n))]


def redact(text: str, secrets: list[str]) -> str:
    """Thay mọi giá trị bí mật dài từ 8 ký tự bằng ***."""
    for s in sorted((s for s in secrets if s and len(s) >= 8), key=len, reverse=True):
        text = text.replace(s, "***")
    return text
