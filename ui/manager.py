"""Quản lý trên giao diện: trả lời người dùng về lượt chạy và biến yêu cầu rõ ràng thành lệnh (FR-16..21).

Không phụ thuộc Chainlit. Lệnh chỉ được áp vào state giữa hai bước của graph (ui/runner.py), qua
app.update_state(config, build_patch(...), as_node=<node vừa xong>): LangGraph tính lại cạnh điều kiện từ node đó,
nên bỏ một finding ngay sau Reviewer thì Dev không còn bị gửi đi sửa nó."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from agents.providers import adapter, load_providers, target_for
from schemas import ManagerReply
from state import MAX_ROUNDS, blocking_findings, open_bugs

MAX_DIGEST_CHARS = 8000
NOTE_ROLES = ("ba", "backend", "frontend", "reviewer", "tester")
ROLE_WORDS = {"ba": ("ba", "business analyst"), "backend": ("backend", "be"), "frontend": ("frontend", "fe"),
              "reviewer": ("reviewer",), "tester": ("tester", "qa")}
ACTION_TITLES = {"stop": "Tạm dừng sau bước đang chạy", "resume": "Chạy tiếp",
                 "dismiss_finding": "Bỏ qua", "add_note": "Ghi chú"}


@dataclass
class Command:
    action: str                       # stop | resume | dismiss_finding | add_note
    ids: list[str] = field(default_factory=list)
    role: str = ""
    note: str = ""

    def describe(self) -> str:
        if self.action == "dismiss_finding":
            why = f" (lý do: {self.note})" if self.note else ""
            return f"Bỏ qua {', '.join(self.ids)}{why}: không còn tính là phải sửa"
        if self.action == "add_note":
            return f"Ghi chú cho {self.role} ở lượt làm kế tiếp: {self.note}"
        return ACTION_TITLES[self.action]


def command_from(reply: ManagerReply) -> Command | None:
    if reply.action == "none":
        return None
    return Command(reply.action, [i.strip().upper() for i in reply.ids if i.strip()], reply.role or "", reply.note.strip())


# ---------- trạng thái đưa cho Quản lý ----------

def _short(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
    return [{k: i[k] for k in keys if k in i} for i in items]


def state_digest(values: dict, running: list[str], paused: bool = False) -> str:
    """Tóm tắt state cho prompt của Quản lý, cắt ở MAX_DIGEST_CHARS (không đưa code)."""
    if not values:
        return "Chưa có lượt chạy nào trong phiên này."
    log = values.get("log", [])
    digest = {
        "du_an": values.get("project_title") or values.get("project"),
        "dang_chay": running or ([] if not paused else ["(tạm dừng)"]),
        "tam_dung": paused,
        "ket_qua": values.get("final_status") or "chưa xong",
        "vong": {"duyet_phan_tich": f"{values.get('review_round', 0)}/{MAX_ROUNDS}",
                 "review_code": f"{values.get('code_review_round', 0)}/{MAX_ROUNDS}",
                 "test": f"{values.get('iteration', 0)}/{MAX_ROUNDS}"},
        "ke_hoach": _short(values.get("plan", []), ("key", "title", "role")),
        "user_stories": _short(values.get("user_stories", []), ("id", "title", "business_rules")),
        "finding_review": _short(values.get("review_findings", []),
                                 ("id", "severity", "owner", "file", "detail", "dismissed")),
        "bug": _short(values.get("bugs", []), ("id", "title", "ref", "owner", "detail", "dismissed")),
        "da_bo_qua": values.get("dismissed") or {},
        "ghi_chu": _short(values.get("manager_notes", []), ("role", "note")),
        "cac_buoc_gan_nhat": [f"{e.get('node')}: {e.get('summary')}" + (f" [{e['data']['model']}]"
                              if (e.get("data") or {}).get("model") else "") for e in log[-20:]],
    }
    text = json.dumps(digest, ensure_ascii=False, indent=1)
    return text if len(text) <= MAX_DIGEST_CHARS else text[:MAX_DIGEST_CHARS] + "\n…(đã cắt bớt)"


def manager_spec(models: dict | None) -> str | None:
    """MODEL_MANAGER trong .env, không có thì dùng model của PM trong lượt chạy (None: model PM theo .env)."""
    return os.getenv("MODEL_MANAGER") or (models or {}).get("pm")


def ask_manager(question: str, values: dict, running: list[str], *, paused: bool = False,
                spec: str | None = None, providers=None) -> tuple[ManagerReply, str]:
    """(trả lời, nhãn model). Chạy được khi graph đang chạy: chỉ đọc state, không ghi gì."""
    providers = providers if providers is not None else load_providers()
    target = target_for("manager", providers, spec=spec or target_for("pm", providers).label)
    if target.provider.type == "mock":
        return mock_reply(question, values), target.label
    prompt = f"Trạng thái lượt chạy:\n{state_digest(values, running, paused)}\n\nNgười dùng: {question}"
    return adapter(target.provider.type)(target, "manager", prompt, ManagerReply), target.label


# ---------- mock: hiểu lệnh theo từ khóa ----------

IDS = re.compile(r"\b(CR|BUG)-?(\d+)\b", re.IGNORECASE)


def mock_reply(question: str, values: dict) -> ManagerReply:
    q = question.lower()
    ids = [f"{a.upper()}-{int(n):02d}" for a, n in IDS.findall(question)]
    if "chạy tiếp" in q or "tiếp tục" in q:
        return ManagerReply(reply="Em sẽ cho team chạy tiếp từ chỗ đã dừng.", action="resume")
    if "dừng" in q:
        return ManagerReply(reply="Em sẽ tạm dừng team sau bước đang chạy, giữ nguyên trạng thái để chạy tiếp.",
                            action="stop")
    if ids and ("bỏ qua" in q or "báo nhầm" in q):
        reason = question.split(",", 1)[1].strip() if "," in question else "người dùng yêu cầu"
        return ManagerReply(reply=f"Em sẽ đánh dấu {', '.join(ids)} là bỏ qua.", action="dismiss_finding",
                            ids=ids, note=reason)
    if "ghi chú" in q or "dặn" in q or "nhớ" in q:
        role = next((r for r, words in ROLE_WORDS.items() if any(re.search(rf"\b{w}\b", q) for w in words)), "")
        note = question.split(":", 1)[1].strip() if ":" in question else question
        if role:
            return ManagerReply(reply=f"Em sẽ dặn {role} ở lượt làm kế tiếp.", action="add_note", role=role, note=note)
        return ManagerReply(reply="Anh muốn dặn role nào: BA, Backend, Frontend, Reviewer hay Tester?", action="none")
    for i in ids:
        item = next((x for x in values.get("review_findings", []) + values.get("bugs", []) if x["id"] == i), None)
        if item:
            return ManagerReply(reply=f"{i} ({item.get('owner')}): {item.get('detail')}", action="none")
    log = values.get("log", [])
    last = f"Bước gần nhất: {log[-1]['node']}: {log[-1]['summary']}" if log else "Chưa có bước nào xong."
    return ManagerReply(reply=f"(Quản lý mock) {last}", action="none")


# ---------- áp lệnh ----------

def validate(cmd: Command, values: dict) -> str | None:
    """Lỗi nếu lệnh không áp được vào state hiện tại; None là được."""
    if cmd.action == "dismiss_finding":
        if not cmd.ids:
            return "chưa nói bỏ qua mã nào"
        known = {f["id"] for f in values.get("review_findings", [])} | {b["id"] for b in values.get("bugs", [])}
        missing = [i for i in cmd.ids if i not in known]
        if missing:
            return f"không thấy {', '.join(missing)} trong finding hay bug hiện tại"
    elif cmd.action == "add_note":
        if cmd.role not in NOTE_ROLES:
            return f"role '{cmd.role}' không nhận ghi chú (chỉ {', '.join(NOTE_ROLES)})"
        if not cmd.note:
            return "ghi chú trống"
    elif cmd.action not in ("stop", "resume"):
        return f"lệnh '{cmd.action}' không có"
    return None


def build_patch(cmd: Command, values: dict, after: str) -> dict:
    """Phần state cần ghi cho lệnh dismiss_finding / add_note (stop, resume không đổi state)."""
    entry = {"action": cmd.action, "text": cmd.describe(), "after": after}
    if cmd.action == "dismiss_finding":
        reason = cmd.note or "người dùng yêu cầu"
        mark = lambda items: [{**x, "dismissed": True, "dismiss_reason": reason} if x["id"] in cmd.ids else x
                              for x in items]
        return {"review_findings": mark(values.get("review_findings", [])), "bugs": mark(values.get("bugs", [])),
                "dismissed": {**(values.get("dismissed") or {}), **{i: reason for i in cmd.ids}},
                "interventions": [entry]}
    if cmd.action == "add_note":
        n = len(values.get("manager_notes", [])) + 1
        return {"manager_notes": [{"id": f"N-{n:02d}", "role": cmd.role, "note": cmd.note,
                                   "at": len(values.get("log", []))}],
                "interventions": [entry]}
    return {}


def effect_after(values: dict) -> str:
    """Một câu nói lệnh vừa áp làm thay đổi gì: còn bao nhiêu finding/bug phải sửa."""
    left_f, left_b = len(blocking_findings(values)), len(open_bugs(values))
    return f"Còn {left_f} finding chặn và {left_b} bug phải sửa."
