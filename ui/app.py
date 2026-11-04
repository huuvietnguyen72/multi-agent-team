"""Giao diện Chainlit theo dõi team AI agent: chat theo role, bảng tiến độ, xem file, chọn model theo role.

    chainlit run ui/app.py        (chạy từ gốc repo, mở http://localhost:8000)

File này chỉ nối các phần đã có: tools/run.py (chuẩn bị lượt chạy), ui/runner.py (sự kiện của graph),
ui/view.py (nội dung hiển thị). Nó không tự quyết nội dung tin nhắn.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import chainlit as cl  # noqa: E402
from chainlit.input_widget import Select, Slider, Switch, TextInput  # noqa: E402

from graph import build_graph  # noqa: E402
from agents.providers import (ESCALATABLE, ROLES, default_specs, escalation_specs, load_providers,  # noqa: E402
                              model_choices)
from tools.project import list_projects, load_project  # noqa: E402
from tools.run import format_models, prepare_run  # noqa: E402
from ui.runner import exclusive_run, stream_events  # noqa: E402
from ui.view import (AUTHORS, Progress, changed_files, files_for, language_for, message_for, redact,  # noqa: E402
                     secret_values, snapshot, summary_text)

KEEP = "(không đổi)"
ROLE_NAMES = {"pm": "PM", "ba": "BA", "backend": "Backend", "frontend": "Frontend",
              "reviewer": "Reviewer", "tester": "Tester"}
TASK_STATUS = {"ready": cl.TaskStatus.READY, "running": cl.TaskStatus.RUNNING,
               "done": cl.TaskStatus.DONE, "failed": cl.TaskStatus.FAILED}
MAX_FILE_CHARS = 100_000
TICK_SECONDS = 5


def _project_title(name: str) -> str:
    try:
        return load_project(name).title
    except (FileNotFoundError, ValueError):
        return name


def _widgets(projects: list[str], current: str | None) -> tuple[list, str | None]:
    """Các ô cài đặt (FR-02, MS-01..MS-03) và lỗi ESCALATE* nếu có."""
    providers = load_providers()
    choices = model_choices(providers)
    defaults = default_specs(providers)
    try:
        esc, esc_error = escalation_specs(), None
    except ValueError as e:
        esc, esc_error = {}, str(e)
    widgets = [
        Select(id="project", label="Dự án", values=projects or ["(chưa có dự án)"],
               initial_value=current or (projects[0] if projects else "(chưa có dự án)")),
        TextInput(id="requirements", label="File requirements",
                  description="Để trống là file của dự án, hoặc đường dẫn tới requirements của một module",
                  initial=""),
        Switch(id="mock", label="Chạy thử (mock), không tốn token",
               initial=all(v == "mock" for v in defaults.values())),
        Slider(id="delay", label="Độ trễ mỗi bước khi chạy mock (giây)", initial=2, min=0, max=10, step=1),
    ]
    for role in ROLES:
        initial = defaults.get(role, "mock")
        widgets.append(Select(id=f"model_{role}", label=f"Model của {ROLE_NAMES[role]}",
                              values=sorted(set(choices) | {initial}), initial_value=initial))
    for role in ESCALATABLE:
        initial = esc.get(role, KEEP)
        widgets.append(Select(id=f"escalate_{role}", label=f"Model vòng sửa cuối của {ROLE_NAMES[role]}",
                              description="Tự đổi sang model này ở lần sửa cuối cùng; bỏ qua khi chạy mock",
                              values=[KEEP] + sorted(set(choices) | ({initial} - {KEEP})), initial_value=initial))
    return widgets, esc_error


@cl.on_chat_start
async def on_chat_start():
    projects = list_projects()
    current = os.getenv("PROJECT") if os.getenv("PROJECT") in projects else (projects[0] if projects else None)
    widgets, esc_error = _widgets(projects, current)
    settings = await cl.ChatSettings(widgets).send()
    cl.user_session.set("settings", dict(settings))
    cl.user_session.set("project", current)
    cl.user_session.set("stop", threading.Event())
    if not projects:
        await cl.Message(content="Chưa có dự án nào. Chép `projects/_template/` thành `projects/<tên>/` rồi tải lại trang.").send()
        return
    actions = [cl.Action(name="pick_project", payload={"project": p}, label=_project_title(p)) for p in projects]
    await cl.Message(content="Xin chào. Chọn một dự án để team bắt đầu làm. Model của từng role nằm trong phần "
                             "cài đặt (biểu tượng bánh răng cạnh ô nhập); thay đổi ở đó không ghi vào `.env`.",
                     actions=actions).send()
    if esc_error:
        await cl.Message(content=f"Cấu hình model vòng sửa cuối chưa đúng, tạm để \"{KEEP}\": {esc_error}").send()


@cl.on_settings_update
async def on_settings_update(settings):
    cl.user_session.set("settings", dict(settings))
    if settings.get("project") in list_projects():
        cl.user_session.set("project", settings["project"])


@cl.action_callback("pick_project")
async def on_pick_project(action: cl.Action):
    name = action.payload.get("project")
    cl.user_session.set("project", name)
    await cl.Message(content=f"Đã chọn **{_project_title(name)}**. Bấm Chạy khi sẵn sàng.",
                     actions=[cl.Action(name="run", payload={}, label="Chạy")]).send()


@cl.on_message
async def on_message(message: cl.Message):
    await cl.Message(content="Bấm nút Chạy để team bắt đầu. Đổi dự án hoặc model trong phần cài đặt.",
                     actions=[cl.Action(name="run", payload={}, label="Chạy")]).send()


@cl.on_stop
async def on_stop():
    stop = cl.user_session.get("stop")
    if stop is not None:
        stop.set()


async def _send_tasks(task_list: cl.TaskList, progress: Progress, status: str) -> None:
    task_list.tasks = [cl.Task(title=title, status=TASK_STATUS[st]) for title, st in progress.rows()]
    task_list.status = status
    await task_list.send()


def _file_actions(paths: list[Path], out_dir: Path, step: int) -> list[cl.Action]:
    """Một nút cho mỗi file của bước; bấm thì nội dung mở ở khung bên phải (FR-08).
    Nội dung được giữ lại đúng như lúc bước này xong, nên bấm lại sau vẫn thấy bản của bước đó."""
    files = cl.user_session.get("files") or {}
    actions = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n\n(đã cắt bớt)"
        rel = p.relative_to(out_dir).as_posix()
        key = f"{step}:{rel}"
        files[key] = (rel, text, language_for(p))
        actions.append(cl.Action(name="show_file", payload={"key": key}, label=rel, icon="file-text"))
    cl.user_session.set("files", files)
    return actions


@cl.action_callback("show_file")
async def on_show_file(action: cl.Action):
    item = (cl.user_session.get("files") or {}).get(action.payload.get("key"))
    if not item:
        return
    rel, text, language = item
    await cl.ElementSidebar.set_elements([cl.Text(name=rel, content=text, language=language)])
    await cl.ElementSidebar.set_title(rel)


async def _tick(msg: cl.Message, author: str, started: float) -> None:
    """Cập nhật số giây của tin tạm "đang làm…" (FR-07)."""
    try:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            msg.content = f"_{author} đang làm… {int(time.monotonic() - started)} giây_"
            await msg.update()
    except asyncio.CancelledError:
        pass


@cl.action_callback("run")
async def on_run(action: cl.Action):
    settings = dict(cl.user_session.get("settings") or {})  # bản sao: đổi cài đặt sau lúc này không ảnh hưởng
    project = cl.user_session.get("project") or settings.get("project")
    mock = bool(settings.get("mock"))
    delay = float(settings.get("delay") or 0)
    models = {r: settings.get(f"model_{r}") or "mock" for r in ROLES}
    escalate = {r: v for r in ESCALATABLE if (v := settings.get(f"escalate_{r}")) and v != KEEP}
    try:
        setup = prepare_run(project, (settings.get("requirements") or "").strip() or None,
                            models=models, escalate=escalate, mock=mock)
    except FileNotFoundError as e:
        await cl.Message(content=str(e)).send()
        return
    if setup.problems:
        await cl.Message(content="Cấu hình model chưa đúng, chưa chạy:\n\n" +
                                 "\n".join(f"- {p}" for p in setup.problems)).send()
        return
    if setup.real_model:
        rows = "\n".join(f"| {ROLE_NAMES[r]} | `{setup.models.get(r, '?')}` | "
                         f"{'`' + setup.escalate[r] + '`' if r in setup.escalate else KEEP} |" for r in ROLES)
        res = await cl.AskActionMessage(
            content=f"**{setup.project.title}** sẽ gọi model thật (tốn token hoặc hạn mức gói):\n\n"
                    f"| Role | Model | Model vòng sửa cuối |\n|---|---|---|\n{rows}",
            actions=[cl.Action(name="confirm", payload={"ok": True}, label="Chạy"),
                     cl.Action(name="cancel", payload={"ok": False}, label="Hủy")],
            timeout=600).send()
        if not res or not (res.get("payload") or {}).get("ok"):
            await cl.Message(content="Đã hủy, chưa gọi model nào.").send()
            return

    with exclusive_run() as ok:
        if not ok:
            await cl.Message(content="Đang có lượt khác chạy. Chờ lượt đó xong rồi bấm Chạy lại.").send()
            return
        await _run(setup, mock=mock, delay=delay)


async def _run(setup, *, mock: bool, delay: float) -> None:
    out_dir = Path(os.environ["OUTPUT_DIR"])
    stop = threading.Event()
    cl.user_session.set("stop", stop)
    secrets = secret_values(load_providers())
    progress = Progress()
    task_list = cl.TaskList()
    await _send_tasks(task_list, progress, "Đang chạy")
    await cl.Message(content=f"Bắt đầu lượt `{setup.run_id}` · {format_models(setup)}").send()

    placeholders: dict[str, cl.Message] = {}
    tickers: dict[str, asyncio.Task] = {}
    before: dict[str, dict] = {}
    started = time.monotonic()
    step = 0
    events = stream_events(build_graph(), setup, stop)
    next_event = cl.make_async(next)
    final_status = "Lỗi"
    while (event := await next_event(events, None)) is not None:
        node = event.node
        if event.kind == "start":
            author = AUTHORS.get(node, node)
            progress.start(node)
            before[node] = snapshot(out_dir)
            msg = cl.Message(author=author, content=f"_{author} đang làm…_")
            await msg.send()
            placeholders[node] = msg
            tickers[node] = asyncio.create_task(_tick(msg, author, time.monotonic()))
            await _send_tasks(task_list, progress, "Đang chạy")
        elif event.kind == "done":
            if mock and delay > 0:
                # chạy mock xong ngay, nên giữ tin "đang làm…" thêm một lúc để người xem kịp thấy ai đang làm;
                # graph chỉ chạy tiếp khi lấy sự kiện kế tiếp, nên chờ ở đây làm chậm cả lượt
                await asyncio.sleep(delay)
            if (t := tickers.pop(node, None)) is not None:
                t.cancel()
            progress.finish(node, event.update)
            step += 1
            files = files_for(node, changed_files(before.pop(node, {}), snapshot(out_dir)), out_dir)
            actions = _file_actions(files, out_dir, step)
            content = message_for(node, event.update)
            if (old := placeholders.pop(node, None)) is not None:
                await old.remove()
            await cl.Message(author=AUTHORS.get(node, node), content=content, actions=actions).send()
            await _send_tasks(task_list, progress, "Đang chạy")
        elif event.kind == "error":
            if node:
                progress.fail(node)
                if (t := tickers.pop(node, None)) is not None:
                    t.cancel()
            text = "Lỗi: " + redact(event.message or "", secrets)
            if node and (msg := placeholders.pop(node, None)) is not None:
                msg.content = text
                await msg.update()
            else:
                await cl.Message(content=text).send()
            final_status = "Lỗi"
        elif event.kind == "end":
            for t in tickers.values():
                t.cancel()
            final = event.final or {}
            if final.get("final_status"):
                final_status = "ACCEPTED" if final["final_status"] == "ACCEPTED" else "Chưa đạt"
                await cl.Message(content=summary_text(final, setup, time.monotonic() - started)).send()
            elif stop.is_set() and final_status != "Lỗi":
                final_status = "Đã dừng"
                await cl.Message(content="Đã dừng sau bước đang chạy.").send()
            elif stop.is_set():
                final_status = "Đã dừng"
            await _send_tasks(task_list, progress, final_status)
            break
