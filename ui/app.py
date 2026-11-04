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
from tools.file_tools import display  # noqa: E402
from tools.run import archive_output, format_models, prepare_run  # noqa: E402
from ui.manager import Command, ask_manager, build_patch, command_from, manager_spec, validate  # noqa: E402
from ui.runner import RunControl, exclusive_run, stream_events  # noqa: E402
from ui.turns import Turns, file_changes  # noqa: E402
from ui.view import (AUTHORS, Progress, changed_files, files_for, language_for, message_for, redact,  # noqa: E402
                     secret_values, snapshot, summary_text)

KEEP = "(không đổi)"
SAME_AS_PM = "(giống PM)"
MANAGER = "Manager"  # tên tác giả tin nhắn của Quản lý; avatar đọc từ public/avatars/manager.png
ROLE_NAMES = {"pm": "PM", "ba": "BA", "backend": "Backend", "frontend": "Frontend",
              "reviewer": "Reviewer", "tester": "Tester"}
TASK_STATUS = {"ready": cl.TaskStatus.READY, "running": cl.TaskStatus.RUNNING,
               "done": cl.TaskStatus.DONE, "failed": cl.TaskStatus.FAILED}
MAX_FILE_CHARS = 100_000
TICK_SECONDS = 5
PANEL_MIN_INTERVAL = 1.0  # cập nhật khung Chi tiết tối đa một lần mỗi giây khi có sự kiện bước


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
    manager = os.getenv("MODEL_MANAGER") or SAME_AS_PM
    widgets.append(Select(id="model_manager", label="Model của Quản lý (chat trong lúc chạy)",
                          description="Trả lời câu hỏi và nhận lệnh trong khung chat; khi chạy mock thì dùng Quản lý mock",
                          values=[SAME_AS_PM] + sorted(set(choices) | ({manager} - {SAME_AS_PM})),
                          initial_value=manager))
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
    await cl.Message(content="**Chọn dự án** để team bắt đầu làm.\n\n"
                             "- Biểu tượng bánh răng cạnh ô nhập: đổi model từng role, hoặc bật chạy thử (mock) "
                             "không tốn token. Thay đổi ở đó không ghi vào `.env`.\n"
                             "- Trong lúc team chạy: gõ vào ô nhập để hỏi Quản lý, hoặc ra lệnh như "
                             "\"dừng lại\", \"bỏ qua CR-02\", \"dặn frontend: ...\".\n"
                             "- Bấm **Chi tiết** dưới tin của một role để xem từng lượt và phần code đã sửa.",
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


def _manager_model(settings: dict, setup) -> str | None:
    """Model của Quản lý: mock khi đang bật chạy thử, ô chọn trong cài đặt, rồi MODEL_MANAGER, rồi model của PM."""
    if settings.get("mock"):
        return "mock"
    chosen = settings.get("model_manager")
    if chosen and chosen != SAME_AS_PM:
        return chosen
    return manager_spec(setup.models if setup else None)


def _run_state() -> tuple[dict, list[str], bool]:
    """(state, node đang chạy, đang tạm dừng) của lượt đang chạy hoặc lượt gần nhất trong phiên."""
    last = cl.user_session.get("last_run")
    if not last:
        return {}, [], False
    graph_app, setup = last
    control: RunControl | None = cl.user_session.get("control")
    values = dict(graph_app.get_state(setup.config).values)
    return values, list(control.running) if control else [], bool(control and control.paused)


@cl.on_message
async def on_message(message: cl.Message):
    """Quản lý trả lời (FR-16); lệnh thì hiện nút xác nhận (FR-18)."""
    settings = cl.user_session.get("settings") or {}
    last = cl.user_session.get("last_run")
    values, running, paused = _run_state()
    started = time.monotonic()
    try:
        reply, label = await cl.make_async(ask_manager)(message.content, values, running, paused=paused,
                                                         spec=_manager_model(settings, last[1] if last else None))
    except Exception as e:  # model lỗi, hết hạn mức, cấu hình sai: báo trong chat, lượt chạy không bị ảnh hưởng
        await cl.Message(author=MANAGER, content="Quản lý lỗi: " +
                         redact(f"{type(e).__name__}: {e}", secret_values(load_providers()))).send()
        return
    footer = f"\n\n_model:_ `{label}` _· {time.monotonic() - started:.1f} giây_"
    cmd = command_from(reply)
    actions = []
    if cmd is not None:
        control: RunControl | None = cl.user_session.get("control")
        error = None if cmd.action in ("stop", "resume") else validate(cmd, values)
        if control is None:
            error = "không có lượt nào đang chạy"
        elif cmd.action == "resume" and not control.paused:
            error = "team đang chạy, không có gì để chạy tiếp"
        if error:
            footer = f"\n\nKhông áp được lệnh: {error}." + footer
        else:
            pending = cl.user_session.get("pending_commands") or {}
            cid = f"c{len(pending) + 1}"
            footer = f"\n\n**Lệnh:** {cmd.describe()}" + footer
            actions = [cl.Action(name="manager_ok", payload={"cid": cid}, label="Đồng ý"),
                       cl.Action(name="manager_no", payload={"cid": cid}, label="Không")]
    if last is None and not actions:  # chưa chạy lần nào: vẫn đưa nút Chạy như trước
        actions = [cl.Action(name="run", payload={}, label="Chạy")]
    msg = cl.Message(author=MANAGER, content=reply.reply + footer, actions=actions)
    await msg.send()
    if cmd is not None and actions and actions[0].name == "manager_ok":
        pending[cid] = (cmd, msg)  # giữ tin nhắn để gỡ cả hai nút khi đã chọn
        cl.user_session.set("pending_commands", pending)


@cl.action_callback("manager_ok")
async def on_manager_ok(action: cl.Action):
    cmd, msg = (cl.user_session.get("pending_commands") or {}).pop(action.payload.get("cid"), (None, None))
    if msg is not None:
        await msg.remove_actions()
    control: RunControl | None = cl.user_session.get("control")
    if cmd is None or control is None:
        await cl.Message(author=MANAGER, content="Lượt chạy đã kết thúc, lệnh không còn tác dụng.").send()
        return
    control.push(cmd)
    when = "ngay" if control.paused else "khi bước đang chạy xong"
    await cl.Message(author=MANAGER, content=f"Đã nhận lệnh, áp dụng {when}: {cmd.describe()}.").send()


@cl.action_callback("manager_no")
async def on_manager_no(action: cl.Action):
    _, msg = (cl.user_session.get("pending_commands") or {}).pop(action.payload.get("cid"), (None, None))
    if msg is not None:
        await msg.remove_actions()
    await cl.Message(author=MANAGER, content="Đã bỏ lệnh, không đổi gì.").send()


@cl.on_stop
async def on_stop():
    # Chainlit tự gửi "Task manually stopped." trước khi gọi hàm này; nói rõ team dừng thế nào.
    stop = cl.user_session.get("stop")
    if stop is not None and not stop.is_set():
        stop.set()
        if (control := cl.user_session.get("control")) is not None:
            control.wake.set()  # đang tạm dừng thì thôi chờ
        await cl.Message(content="Đã nhận lệnh dừng: team dừng sau khi bước đang chạy xong, "
                                 "không gọi thêm model nào.").send()


async def _send_tasks(task_list: cl.TaskList, progress: Progress, status: str) -> None:
    task_list.tasks = [cl.Task(title=title, status=TASK_STATUS[st]) for title, st in progress.rows()]
    task_list.status = status
    await task_list.send()


def _file_actions(paths: list[Path], out_dir: Path, step: int, stats: dict[str, tuple[int, int]]) -> list[cl.Action]:
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
        added, removed = stats.get(rel, (0, 0))
        label = f"{rel}  +{added} -{removed}" if added or removed else rel
        actions.append(cl.Action(name="show_file", payload={"key": key}, label=label, icon="file-text"))
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


def _detail_action(author: str) -> cl.Action:
    return cl.Action(name="show_role", payload={"role": author}, label="Chi tiết", icon="list")


async def _show_panel(role: str) -> None:
    turns: Turns = cl.user_session.get("turns") or Turns()
    el = cl.CustomElement(name="RoleDetail", props=turns.props(role, time.monotonic()), display="side")
    cl.user_session.set("panel", {"role": role, "element": el, "sent": time.monotonic()})
    await cl.ElementSidebar.set_elements([el])
    await cl.ElementSidebar.set_title(f"Chi tiết {role}")


async def _refresh_panel(role: str, force: bool = True) -> None:
    """Vẽ lại khung Chi tiết nếu nó đang mở cho `role` (FR-13, FR-14)."""
    panel = cl.user_session.get("panel")
    if not panel or panel["role"] != role:
        return
    if not force and time.monotonic() - panel["sent"] < PANEL_MIN_INTERVAL:
        return
    await _show_panel(role)


@cl.action_callback("show_role")
async def on_show_role(action: cl.Action):
    await _show_panel(action.payload.get("role") or "PM")


@cl.action_callback("close_role")
async def on_close_role(action: cl.Action):
    cl.user_session.set("panel", None)
    await cl.ElementSidebar.set_elements([])


async def _tick(msg: cl.Message, author: str, started: float) -> None:
    """Cập nhật số giây của tin tạm "đang làm…" (FR-07) và của khung Chi tiết nếu đang mở."""
    try:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            msg.content = f"_{author} đang làm… {int(time.monotonic() - started)} giây_"
            await msg.update()
            await _refresh_panel(author)
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
        # AskActionMessage xong thì Chainlit báo "đang chạy" (task_start), khung nhập bị khóa và nút gửi thành nút
        # dừng cho tới hết lượt. Trả khung nhập lại để chat được với Quản lý trong lúc team chạy.
        await cl.context.emitter.task_end()
        if not res or not (res.get("payload") or {}).get("ok"):
            await cl.Message(content="Đã hủy, chưa gọi model nào.").send()
            return

    with exclusive_run() as ok:
        if not ok:
            await cl.Message(content="Đang có lượt khác chạy. Chờ lượt đó xong rồi bấm Chạy lại.").send()
            return
        try:
            await _run(setup, mock=mock, delay=delay)
        finally:
            cl.user_session.set("stop", None)  # hết lượt: bấm dừng lúc này không còn gì để dừng
            cl.user_session.set("control", None)


async def _run(setup, *, mock: bool, delay: float) -> None:
    out_dir = Path(os.environ["OUTPUT_DIR"])
    stop = threading.Event()
    cl.user_session.set("stop", stop)
    secrets = secret_values(load_providers())
    progress = Progress()
    turns = Turns()
    cl.user_session.set("turns", turns)
    task_list = cl.TaskList()
    await _send_tasks(task_list, progress, "Đang chạy")
    moved = archive_output(out_dir, setup.run_id)
    note = f"\n\nĐầu ra lượt trước đã chuyển sang `{display(moved)}`." if moved else ""
    await cl.Message(content=f"Bắt đầu lượt `{setup.run_id}` · {format_models(setup, code=True)}{note}").send()

    placeholders: dict[str, cl.Message] = {}
    tickers: dict[str, asyncio.Task] = {}
    before: dict[str, dict] = {}
    started = time.monotonic()
    step = 0
    graph_app = build_graph()
    control = RunControl(apply=build_patch, validate=validate)
    cl.user_session.set("control", control)
    cl.user_session.set("last_run", (graph_app, setup))
    events = stream_events(graph_app, setup, stop, control)
    next_event = cl.make_async(next)
    final_status = "Lỗi"
    while (event := await next_event(events, None)) is not None:
        node = event.node
        if event.kind == "start":
            author = AUTHORS.get(node, node)
            progress.start(node)
            turns.start(node, event.data or {}, time.monotonic())
            before[node] = snapshot(out_dir)
            msg = cl.Message(author=author, content=f"_{author} đang làm…_", actions=[_detail_action(author)])
            await msg.send()
            placeholders[node] = msg
            tickers[node] = asyncio.create_task(_tick(msg, author, time.monotonic()))
            await _send_tasks(task_list, progress, "Đang chạy")
            await _refresh_panel(author)
        elif event.kind == "progress":
            turns.progress(node, event.data or {})
            await _refresh_panel(AUTHORS.get(node, node), force=False)
        elif event.kind == "done":
            if mock and delay > 0:
                # chạy mock xong ngay, nên giữ tin "đang làm…" thêm một lúc để người xem kịp thấy ai đang làm;
                # graph chỉ chạy tiếp khi lấy sự kiện kế tiếp, nên chờ ở đây làm chậm cả lượt
                await asyncio.sleep(delay)
            if (t := tickers.pop(node, None)) is not None:
                t.cancel()
            progress.finish(node, event.update)
            step += 1
            snap_before, snap_after = before.pop(node, {}), snapshot(out_dir)
            files = files_for(node, changed_files(snap_before, snap_after), out_dir)
            changes = file_changes(node, snap_before, snap_after, out_dir)
            log_data = ((event.update.get("log") or [{}])[-1] or {}).get("data") or {}
            turns.finish(node, changes, log_data, time.monotonic())
            actions = _file_actions(files, out_dir, step, {c.path: (c.added, c.removed) for c in changes})
            actions.append(_detail_action(AUTHORS.get(node, node)))
            content = message_for(node, event.update)
            if (old := placeholders.pop(node, None)) is not None:
                await old.remove()
            await cl.Message(author=AUTHORS.get(node, node), content=content, actions=actions).send()
            await _send_tasks(task_list, progress, "Đang chạy")
            await _refresh_panel(AUTHORS.get(node, node))
        elif event.kind == "error":
            if node:
                progress.fail(node)
                turns.fail(node, time.monotonic())
                await _refresh_panel(AUTHORS.get(node, node))
                if (t := tickers.pop(node, None)) is not None:
                    t.cancel()
            text = "Lỗi: " + redact(event.message or "", secrets)
            if node and (msg := placeholders.pop(node, None)) is not None:
                msg.content = text
                await msg.update()
            else:
                await cl.Message(content=text).send()
            final_status = "Lỗi"
        elif event.kind == "applied":
            await cl.Message(author=MANAGER, content=f"Đã áp dụng sau bước {AUTHORS.get(node, node)}: {event.message}.").send()
        elif event.kind == "rejected":
            await cl.Message(author=MANAGER, content=f"Không áp được lệnh: {event.message}.").send()
        elif event.kind == "paused":
            await _send_tasks(task_list, progress, "Tạm dừng")
            await cl.Message(author=MANAGER, content=f"Đã tạm dừng sau bước {AUTHORS.get(node, node)}. "
                                                     "Gõ \"chạy tiếp\" để tiếp tục, hoặc ra lệnh khác trước.").send()
        elif event.kind == "resumed":
            await _send_tasks(task_list, progress, "Đang chạy")
            await cl.Message(author=MANAGER, content="Team chạy tiếp.").send()
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
