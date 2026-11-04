"""Giao diện Chainlit theo dõi team AI agent: chat theo role, bảng tiến độ, xem file, chọn model theo role.

    chainlit run ui/app.py        (chạy từ gốc repo, mở http://localhost:8000)

File này chỉ nối các phần đã có: tools/run.py (chuẩn bị lượt chạy), ui/runner.py (sự kiện của graph),
ui/view.py (nội dung hiển thị). Nó không tự quyết nội dung tin nhắn.
"""
from __future__ import annotations

import asyncio
import logging
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

from ui.history import auth_secret, check_login, credentials, load_run, make_data_layer, save_run  # noqa: E402

os.environ["CHAINLIT_AUTH_SECRET"] = auth_secret()  # Chainlit cần khóa này khi có đăng nhập

import chainlit as cl  # noqa: E402
from chainlit.data import get_data_layer as current_data_layer  # noqa: E402
from chainlit.input_widget import Select, Slider, Switch, TextInput  # noqa: E402

from graph import build_graph  # noqa: E402
from agents.providers import (ESCALATABLE, ROLES, default_specs, escalation_specs, load_providers,  # noqa: E402
                              model_choices)
from tools.project import list_projects, load_module, load_project, write_module, write_project  # noqa: E402
from tools.file_tools import display  # noqa: E402
from tools.run import archive_output, format_models, prepare_run  # noqa: E402
from ui.code import read_file, source_for_run, source_root, sources, tree  # noqa: E402
from ui.projects import (MODULE_TAG, description, draft_module, draft_project, modules_of, overview,  # noqa: E402
                         unique_slug)
from ui.manager import Command, ask_manager, build_patch, command_from, manager_spec, validate  # noqa: E402
from ui.runner import RunControl, exclusive_run, stream_events  # noqa: E402
from ui.turns import Turns, file_changes  # noqa: E402
from ui.view import (AUTHORS, Progress, changed_files, files_for, language_for, message_for, redact,  # noqa: E402
                     secret_values, snapshot, summary_text)

KEEP = "(không đổi)"
SAME_AS_PM = "(giống PM)"
NEW_PROJECT = "+ Dự án mới"  # mục cuối của ô chọn dự án (chat profile) ở góc trên
MANAGER = "Manager"  # tên tác giả tin nhắn của Quản lý; avatar đọc từ public/avatars/manager.png
ROLE_NAMES = {"pm": "PM", "ba": "BA", "backend": "Backend", "frontend": "Frontend",
              "reviewer": "Reviewer", "tester": "Tester"}
TASK_STATUS = {"ready": cl.TaskStatus.READY, "running": cl.TaskStatus.RUNNING,
               "done": cl.TaskStatus.DONE, "failed": cl.TaskStatus.FAILED}
MAX_FILE_CHARS = 100_000
TICK_SECONDS = 5
RESUME_DELAY = 1.0  # giây
PANEL_MIN_INTERVAL = 1.0  # cập nhật khung Chi tiết tối đa một lần mỗi giây khi có sự kiện bước


class _NoElementStorage(logging.Filter):
    """Không lưu file đính kèm (bảng tiến độ, nội dung file) vào lịch sử: code đã nằm trong output/, nên bỏ cảnh báo
    "storage client is not initialized" mà Chainlit in ra mỗi lần gửi phần tử."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "storage client is not initialized" not in msg and "No blob_storage_client" not in msg


logging.getLogger("chainlit").addFilter(_NoElementStorage())


class _Unsaved:
    """Giữ dữ liệu lớn trong user_session mà không lưu vào lịch sử: Chainlit ghi user_session (phần đổi được sang
    JSON) vào metadata của cuộc chat và xóa sạch metadata nếu nó lớn hơn 1 MB."""

    def __init__(self, value):
        self.value = value


def _get_unsaved(key: str, default=None):
    box = cl.user_session.get(key)
    return box.value if isinstance(box, _Unsaved) else default


def _set_unsaved(key: str, value) -> None:
    cl.user_session.set(key, _Unsaved(value))
_user, _, _default_password = credentials()
if _default_password:
    print(f"Giao diện: đăng nhập bằng {_user}/{_user}. Đặt UI_USERNAME và UI_PASSWORD trong .env để đổi.")


@cl.data_layer
def _data_layer():
    """Lịch sử chat lưu ở .chainlit/history.db (ui/history.py)."""
    return make_data_layer()


@cl.password_auth_callback
def _login(username: str, password: str) -> cl.User | None:
    return cl.User(identifier=username, metadata={"role": "admin"}) if check_login(username, password) else None


def _project_title(name: str) -> str:
    try:
        return load_project(name).title
    except (FileNotFoundError, ValueError):
        return name


def _widgets() -> tuple[list, str | None]:
    """Các ô cài đặt (FR-02, MS-01..MS-03) và lỗi ESCALATE* nếu có."""
    providers = load_providers()
    choices = model_choices(providers)
    defaults = default_specs(providers)
    try:
        esc, esc_error = escalation_specs(), None
    except ValueError as e:
        esc, esc_error = {}, str(e)
    widgets = [
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


@cl.set_chat_profiles
async def _projects(user: cl.User | None = None, language: str | None = None) -> list[cl.ChatProfile]:
    """Ô chọn dự án ở góc trên (giống Project của Claude): mỗi dự án trong projects/ là một mục, mục cuối là tạo
    dự án mới. Đọc lại mỗi lần tải trang, nên dự án vừa tạo hiện ra sau khi tải lại."""
    names = list_projects()
    default = os.getenv("PROJECT") if os.getenv("PROJECT") in names else (names[0] if names else None)
    profiles = [cl.ChatProfile(name=n, display_name=_project_title(n), default=n == default,
                               markdown_description=description(n, 160) or f"`projects/{n}/`") for n in names]
    profiles.append(cl.ChatProfile(name=NEW_PROJECT, default=not names,
                                   markdown_description="Mô tả ý tưởng, PM soạn requirements và stack cho anh duyệt."))
    return profiles


async def _sidebar(elements: list, title: str) -> None:
    """Mở khung bên phải với `elements` và tiêu đề `title`. Bấm nút đầu tiên của một cuộc chat làm giao diện chuyển
    sang địa chỉ /thread/<id> và mất tiêu đề vừa đặt, nên đặt lại tiêu đề sau một lúc."""
    await cl.ElementSidebar.set_elements(elements, key=f"k{time.monotonic_ns()}")
    await cl.ElementSidebar.set_title(title)

    async def again():
        await asyncio.sleep(1.0)
        await cl.ElementSidebar.set_title(title)

    asyncio.create_task(again())


def _project_actions(name: str | None = None) -> list[cl.Action]:
    """Nút trên trang dự án. Có `name` thì thêm một nút cho mỗi module chưa có cuộc chat (module đã có cuộc chat
    thì trang dự án có đường dẫn tới cuộc chat đó)."""
    actions = [cl.Action(name="run", payload={}, label="Chạy cả dự án"),
               cl.Action(name="module_new", payload={}, label="+ Module mới", icon="plus"), _code_action(),
               cl.Action(name="project_edit", payload={}, label="Yêu cầu và stack", icon="file-pen")]
    if name:
        actions += [cl.Action(name="module_open", payload={"name": m["name"]}, label=f"Module: {m['title']}",
                              icon="square-stack") for m in modules_of(name, _user_id()) if not m["thread"]]
    return actions


def _module_actions() -> list[cl.Action]:
    return [cl.Action(name="run", payload={}, label="Chạy module"), _code_action(),
            cl.Action(name="module_edit", payload={}, label="Yêu cầu module", icon="file-pen")]


def _module():
    """Module của cuộc chat này (None nếu cuộc chat làm cả dự án)."""
    project, name = cl.user_session.get("project"), cl.user_session.get("module")
    if not (project and name):
        return None
    try:
        return load_module(project, name)
    except FileNotFoundError:
        return None


def _chat_title() -> str:
    """Tên gốc của cuộc chat: tên module, hoặc tên dự án."""
    m = _module()
    return m.title if m else _project_title(cl.user_session.get("project") or "")


def _user_id() -> str:
    user = cl.context.session.user
    return user.identifier if user else ""


async def _send_settings() -> str | None:
    widgets, esc_error = _widgets()
    settings = await cl.ChatSettings(widgets).send()
    cl.user_session.set("settings", dict(settings))
    return esc_error


async def _project_home(name: str) -> None:
    """Tin chào của dự án: tổng quan, các lượt và cuộc chat trước, nút Chạy / Mã nguồn / Yêu cầu và stack."""
    text = overview(name, _user_id(), current_thread=cl.context.session.thread_id)
    text += ("\n\n---\nLàm từng phần: bấm **+ Module mới**, mô tả phần cần làm, PM soạn yêu cầu cho anh duyệt, rồi "
             "chạy trong một cuộc chat riêng. Lượt chạy module giữ code đang có và làm tiếp trên đó. **Chạy cả dự án** "
             "thì team làm lại từ đầu theo `requirements.md` (code cũ chuyển sang lượt trước). Bánh răng cạnh ô nhập: "
             "đổi model từng role hoặc bật chạy thử (mock). Trong lúc chạy, gõ vào ô nhập để hỏi Quản lý hoặc ra lệnh "
             "như \"dừng lại\", \"bỏ qua CR-02\".")
    await cl.Message(content=text, actions=_project_actions(name)).send()


@cl.on_chat_start
async def on_chat_start():
    profile = cl.user_session.get("chat_profile")
    names = list_projects()
    cl.user_session.set("stop", threading.Event())
    cl.user_session.set("module", None)
    esc_error = await _send_settings()
    if profile in names:
        cl.user_session.set("project", profile)
        await _project_home(profile)
    else:
        cl.user_session.set("project", None)
        cl.user_session.set("mode", "create")
        await cl.Message(content="## Dự án mới\n\nMô tả phần mềm anh muốn làm trong vài câu: ai dùng, làm được gì, "
                                 "quy tắc quan trọng, công nghệ nếu có (không nói thì PM chọn FastAPI + HTML/JS). "
                                 "PM soạn `requirements.md` và `stack.md` ở khung bên phải để anh sửa rồi bấm Lưu.\n\n"
                                 "Ví dụ: _Quản lý kho cho cửa hàng nhỏ: nhân viên nhập xuất hàng, chủ xem tồn kho, "
                                 "không xuất quá số đang có._").send()
    if esc_error:
        await cl.Message(content=f"Cấu hình model vòng sửa cuối chưa đúng, tạm để \"{KEEP}\": {esc_error}").send()


@cl.on_settings_update
async def on_settings_update(settings):
    cl.user_session.set("settings", dict(settings))


# ---------- tạo và sửa dự án ----------

def _draft_model(settings: dict) -> str | None:
    """Model soạn dự án: mock khi bật chạy thử, không thì model của PM trong cài đặt."""
    return "mock" if settings.get("mock") else settings.get("model_pm")


async def _show_editor(mode: str, data: dict, error: str = "") -> None:
    version = (cl.user_session.get("editor_version") or 0) + 1
    cl.user_session.set("editor_version", version)
    props = {"mode": mode, "version": version, "error": error, **{k: data.get(k, "") for k in
             ("name", "title", "requirements", "stack", "test_command")}}
    cl.user_session.set("panel", {"kind": "editor"})
    title = {"create": "Dự án mới", "module": "Module mới"}.get(mode) or \
        f"{'Sửa module' if mode == 'module_edit' else 'Sửa dự án'} · {data.get('title', '')}"
    await _sidebar([cl.CustomElement(name="ProjectEditor", props=props, display="side")], title)


async def _draft(idea: str, module: bool = False) -> None:
    """PM soạn bản nháp dự án mới (hoặc module mới của dự án đang mở) từ `idea`, rồi mở khung soạn."""
    settings = cl.user_session.get("settings") or {}
    previous = _get_unsaved("draft")
    started = time.monotonic()
    project = cl.user_session.get("project")
    wait = cl.Message(author="PM", content=f"_PM đang soạn {'module' if module else 'dự án'}…_")
    await wait.send()
    try:
        if module:
            draft, label = await cl.make_async(draft_module)(project, idea, previous=previous,
                                                             spec=_draft_model(settings))
        else:
            draft, label = await cl.make_async(draft_project)(idea, previous=previous, spec=_draft_model(settings))
    except Exception as e:
        await wait.remove()
        await cl.Message(author="PM", content="Không soạn được: " +
                         redact(f"{type(e).__name__}: {e}", secret_values(load_providers()))).send()
        return
    data = draft.model_dump()
    if module:
        folder = load_project(project).dir / "modules"
        data["name"] = (previous or {}).get("name") or unique_slug(draft.slug or draft.title, folder, ".md")
    else:
        data["name"] = (previous or {}).get("name") or unique_slug(draft.slug or draft.title)
    _set_unsaved("draft", data)
    await wait.remove()  # gửi tin mới thay vì sửa tin chờ: tin sửa ngay sau khi gửi có thể không vào lịch sử
    button = "Lưu module" if module else "Lưu và tạo dự án"
    await cl.Message(author="PM", content=f"{draft.reply}\n\nBản nháp **{draft.title}** đã mở ở khung bên phải. Sửa "
                     f"trực tiếp rồi bấm **{button}**, hoặc gõ yêu cầu sửa để PM soạn lại."
                     f"\n\n_model:_ `{label}` _· {time.monotonic() - started:.0f} giây_").send()
    await _show_editor("module" if module else "create", data)


def _name_once() -> None:
    """Cuộc chat bắt đầu bằng một nút (không phải tin nhắn) thì Chainlit lấy tên nút làm tên cuộc chat; đổi sang
    tên dự án. Lượt chạy đặt lại tên kèm mã lượt."""
    name = cl.user_session.get("project")
    if name and not cl.user_session.get("named"):
        cl.user_session.set("named", True)
        asyncio.create_task(_name_thread(_chat_title(), wait=1.0))


@cl.action_callback("project_edit")
async def on_project_edit(action: cl.Action):
    _name_once()
    name = cl.user_session.get("project")
    try:
        p = load_project(name)
    except (FileNotFoundError, ValueError, TypeError):
        await cl.Message(content="Chưa có dự án nào đang mở.").send()
        return
    await _show_editor("edit", {"name": p.name, "title": p.title, "requirements": p.requirements,
                                "stack": p.stack, "test_command": p.test_command or ""})


@cl.action_callback("project_save")
async def on_project_save(action: cl.Action):
    d = action.payload or {}
    if d.get("mode") in ("module", "module_edit"):
        await _save_module(d)
        return
    create = d.get("mode") == "create"
    name = (d.get("name") or "").strip() if create else cl.user_session.get("project")
    try:
        p = write_project(name, title=d.get("title", ""), requirements=d.get("requirements", ""),
                          stack=d.get("stack", ""), test_command=d.get("test_command", ""), create=create)
    except (ValueError, FileExistsError, OSError) as e:
        await _show_editor(d.get("mode") or "edit", d, error=str(e))
        return
    if not create:
        await _show_editor("edit", {**d, "name": p.name}, error="")
        await cl.Message(content=f"Đã lưu `projects/{p.name}/`. Lượt chạy sau dùng bản mới.").send()
        return
    cl.user_session.set("project", p.name)
    cl.user_session.set("mode", None)
    _set_unsaved("draft", None)
    await cl.ElementSidebar.set_elements([])
    await _name_thread(p.title, tag=p.name)
    await cl.Message(content=f"Đã tạo dự án **{p.title}** ở `projects/{p.name}/`. Bấm **Chạy cả dự án** để team làm "
                             "ngay trong cuộc chat này, hoặc **+ Module mới** để làm từng phần. Lần sau mở dự án ở ô "
                             "chọn trên cùng (tải lại trang để thấy nó).",
                     actions=_project_actions()).send()


# ---------- module: mỗi module một cuộc chat ----------

@cl.action_callback("module_new")
async def on_module_new(action: cl.Action):
    project = cl.user_session.get("project")
    if not project:
        await cl.Message(content="Chọn một dự án ở ô trên cùng trước.").send()
        return
    if cl.user_session.get("module") or cl.user_session.get("run_ref"):
        await cl.Message(content="Cuộc chat này đã dùng cho một lượt chạy. Mở cuộc chat mới (nút bút chì ở góc trái, "
                                 "rồi chọn dự án) để tạo module, mỗi module một cuộc chat.").send()
        return
    _name_once()
    cl.user_session.set("mode", "module")
    _set_unsaved("draft", None)
    await cl.Message(content=f"## Module mới của {_project_title(project)}\n\nMô tả phần anh muốn làm tiếp trong vài "
                             "câu: chức năng nào, cho ai, quy tắc gì. PM soạn yêu cầu của module ở khung bên phải để "
                             "anh sửa rồi bấm Lưu. Cuộc chat này sẽ thành cuộc chat của module đó.\n\nVí dụ: _Giỏ hàng: "
                             "khách thêm, sửa số lượng, xóa sản phẩm; tối đa 5 cái mỗi sản phẩm._").send()


async def _enter_module(module) -> None:
    """Cuộc chat này thành cuộc chat của `module`: đổi tên, gắn tag, hiện nút chạy."""
    cl.user_session.set("module", module.name)
    cl.user_session.set("mode", None)
    cl.user_session.set("named", True)
    await _name_thread(module.title)
    await cl.Message(content=f"## Module: {module.title}\n\nYêu cầu ở `modules/{module.name}.md`. Bấm **Chạy module** "
                             "để team làm module này tiếp trên code đang có của dự án. Mỗi lần chạy, bản code trước "
                             "được giữ trong Mã nguồn (chọn lượt cũ) để so sánh.",
                     actions=_module_actions()).send()


@cl.action_callback("module_open")
async def on_module_open(action: cl.Action):
    project = cl.user_session.get("project")
    if cl.user_session.get("module") or cl.user_session.get("run_ref"):
        await cl.Message(content="Cuộc chat này đã có lượt chạy. Mở cuộc chat mới để làm module khác.").send()
        return
    try:
        module = load_module(project, action.payload.get("name", ""))
    except (FileNotFoundError, TypeError):
        await cl.Message(content="Không còn module này.").send()
        return
    await _enter_module(module)


@cl.action_callback("module_edit")
async def on_module_edit(action: cl.Action):
    module = _module()
    if module is None:
        await cl.Message(content="Cuộc chat này chưa gắn với module nào.").send()
        return
    await _show_editor("module_edit", {"name": module.name, "title": module.title,
                                       "requirements": module.requirements})


async def _save_module(d: dict) -> None:
    project = cl.user_session.get("project")
    create = d.get("mode") == "module"
    name = (d.get("name") or "").strip() if create else cl.user_session.get("module")
    try:
        module = write_module(project, name, title=d.get("title", ""), requirements=d.get("requirements", ""),
                              create=create)
    except (ValueError, FileExistsError, FileNotFoundError, OSError, TypeError) as e:
        await _show_editor(d.get("mode"), d, error=str(e))
        return
    _set_unsaved("draft", None)
    if not create:
        await _show_editor("module_edit", {"name": module.name, "title": module.title,
                                           "requirements": module.requirements})
        await _name_thread(module.title)
        await cl.Message(content=f"Đã lưu `modules/{module.name}.md`. Lượt chạy sau dùng bản mới.").send()
        return
    await cl.ElementSidebar.set_elements([])
    await _enter_module(module)


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
    if not last:  # cuộc chat mở lại từ lịch sử: state đã lưu của lượt đó
        return _get_unsaved("history_values", {}), [], False
    graph_app, setup = last
    control: RunControl | None = cl.user_session.get("control")
    values = dict(graph_app.get_state(setup.config).values)
    return values, list(control.running) if control else [], bool(control and control.paused)


@cl.on_message
async def on_message(message: cl.Message):
    """Quản lý trả lời (FR-16); lệnh thì hiện nút xác nhận (FR-18). Ở mục "Dự án mới" thì tin nhắn là ý tưởng
    (hoặc yêu cầu sửa bản nháp) cho PM soạn dự án."""
    if cl.user_session.get("mode") in ("create", "module"):
        await _draft(message.content, module=cl.user_session.get("mode") == "module")
        return
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
    files = _get_unsaved("files", {})
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
    _set_unsaved("files", files)
    return actions


@cl.action_callback("show_file")
async def on_show_file(action: cl.Action):
    item = _get_unsaved("files", {}).get(action.payload.get("key"))
    if not item:
        return
    rel, text, language = item
    await _sidebar([cl.Text(name=rel, content=text, language=language)], rel)


def _detail_action(author: str) -> cl.Action:
    return cl.Action(name="show_role", payload={"role": author}, label="Chi tiết", icon="list")


async def _show_panel(role: str) -> None:
    turns: Turns = cl.user_session.get("turns") or Turns()
    el = cl.CustomElement(name="RoleDetail", props=turns.props(role, time.monotonic()), display="side")
    cl.user_session.set("panel", {"role": role, "element": el, "sent": time.monotonic()})
    await _sidebar([el], f"Chi tiết {role}")


async def _refresh_panel(role: str, force: bool = True) -> None:
    """Vẽ lại khung Chi tiết nếu nó đang mở cho `role` (FR-13, FR-14)."""
    panel = cl.user_session.get("panel")
    if not panel or panel.get("role") != role:
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


# ---------- khung Mã nguồn ----------

def _code_action() -> cl.Action:
    return cl.Action(name="show_code", payload={}, label="Mã nguồn", icon="folder-tree")


def _output_dir() -> Path | None:
    """output/ của dự án đang chọn (hoặc của lượt đang xem lại)."""
    name = cl.user_session.get("project") or (cl.user_session.get("settings") or {}).get("project")
    try:
        return load_project(name).output_dir if name else None
    except (FileNotFoundError, ValueError):
        return None


def _code_root(source: str) -> Path | None:
    out_dir = _output_dir()
    return source_root(out_dir, source) if out_dir else None


def _code_file(root: Path | None, path: str | None) -> dict | None:
    """{"path", "content", "language", "size"} của file `path` trong `root`, {"path", "error"} nếu không đọc được."""
    if not root or not path:
        return None
    got = read_file(root, path)
    if got is None:
        return {"path": path, "error": "Không đọc được file (đã bị xóa hoặc ở ngoài thư mục dự án)."}
    text, lang = got
    return {"path": path, "content": text, "language": lang, "size": len(text.encode("utf-8"))}


async def _show_code(source: str | None = None, path: str | None = None) -> None:
    out_dir = _output_dir()
    if out_dir is None:
        await cl.Message(content="Chưa chọn dự án nào nên chưa có mã nguồn để xem.").send()
        return
    items = sources(out_dir)
    panel = cl.user_session.get("panel") or {}
    if source is None:
        source = panel.get("source") if panel.get("kind") == "code" else None
    if source is None or not any(s["id"] == source for s in items):
        run = cl.user_session.get("run_ref") or {}
        source = source_for_run(out_dir, run.get("run_id"))
    root = source_root(out_dir, source)
    files, truncated = tree(root) if root else ([], False)
    if path is None and panel.get("kind") == "code" and panel.get("source") == source:
        path = panel.get("path")  # vẽ lại: giữ file đang xem
    file = _code_file(root, path)
    if file and "error" in file:
        file = None
    props = {"sources": [{"id": s["id"], "label": s["label"]} for s in items] or [{"id": source, "label": "output/"}],
             "source": source, "files": files, "truncated": truncated, "file": file}
    cl.user_session.set("panel", {"kind": "code", "source": source, "path": file and file["path"],
                                  "sent": time.monotonic()})
    title = "Mã nguồn"
    if name := cl.user_session.get("project"):
        try:
            title = f"Mã nguồn · {load_project(name).title}"
        except (FileNotFoundError, ValueError):
            pass
    await _sidebar([cl.CustomElement(name="CodeBrowser", props=props, display="side")], title)


async def _refresh_code() -> None:
    """Có file mới ghi trong lúc chạy: vẽ lại khung Mã nguồn nếu đang mở bản mới nhất."""
    panel = cl.user_session.get("panel")
    if panel and panel.get("kind") == "code" and panel.get("source") == "output":
        await _show_code("output")


@cl.action_callback("show_code")
async def on_show_code(action: cl.Action):
    _name_once()
    await _show_code(action.payload.get("source"))


@cl.action_callback("code_tree")
async def on_code_tree(action: cl.Action):
    """Khung Mã nguồn đổi bản đầu ra: trả về cây file, không vẽ lại khung."""
    source = action.payload.get("source") or "output"
    root = _code_root(source)
    files, truncated = tree(root) if root else ([], False)
    panel = cl.user_session.get("panel") or {}
    cl.user_session.set("panel", {**panel, "kind": "code", "source": source})
    return {"files": files, "truncated": truncated}


@cl.action_callback("code_read")
async def on_code_read(action: cl.Action):
    """Khung Mã nguồn mở một file: trả về nội dung, không vẽ lại khung."""
    source, path = action.payload.get("source") or "output", action.payload.get("path") or ""
    file = _code_file(_code_root(source), path)
    panel = cl.user_session.get("panel") or {}
    cl.user_session.set("panel", {**panel, "kind": "code", "source": source,
                                  "path": path if file and "error" not in file else None})
    return file


# ---------- lịch sử ----------

async def _name_thread(name: str, wait: float = 0.0, tag: str | None = None) -> None:
    """Tên cuộc chat ở thanh bên trái và tag tên dự án (để trang dự án liệt kê các cuộc chat của nó). Mặc định
    Chainlit đặt tên theo nút hay tin nhắn đầu tiên trong một task chạy song song, nên lần đầu thì chờ `wait` giây."""
    if (dl := current_data_layer()) is None or not (tid := cl.context.session.thread_id):
        return
    tag = tag or cl.user_session.get("project")
    tags = [tag] if tag else []
    if tag and (module := cl.user_session.get("module")):
        tags.append(f"{MODULE_TAG}{module}")  # trang dự án tìm cuộc chat của module theo tag này
    try:
        await asyncio.sleep(wait)
        await dl.update_thread(thread_id=tid, name=name, tags=tags or None)
        # sự kiện này làm thanh bên trái tải lại danh sách cuộc chat
        await cl.context.emitter.emit("first_interaction", {"interaction": name, "thread_id": tid})
    except Exception:  # lịch sử lỗi không được làm hỏng lượt chạy
        logging.getLogger(__name__).exception("Không đổi được tên cuộc chat")


def _save_run(setup, graph_app, turns: Turns) -> None:
    try:
        values = dict(graph_app.get_state(setup.config).values)
        save_run(setup.run_id, values, turns, project=setup.project.name)
    except Exception:
        logging.getLogger(__name__).exception("Không lưu được kết quả lượt chạy")


@cl.on_chat_resume
async def on_chat_resume(thread: dict):
    """Mở lại cuộc chat cũ: Chainlit tự vẽ lại tin nhắn và trả user_session đã lưu (cài đặt, dự án, lượt chạy).
    Nút dưới tin cũ không được lưu, nên gửi một tin có nút Chi tiết / Mã nguồn cho lượt đó."""
    # Tin "Đã mở lại lượt ..." của lần mở trước: bỏ khỏi lịch sử để không chồng lên nhau. `thread` chính là dữ liệu
    # Chainlit gửi cho giao diện sau hàm này, nên bỏ ở đây là giao diện không thấy nữa.
    old = [st for st in thread.get("steps", []) if (st.get("metadata") or {}).get("resume_notice")]
    thread["steps"] = [st for st in thread.get("steps", []) if st not in old]
    if old and (dl := current_data_layer()) is not None:
        for st in old:
            await dl.delete_step(st["id"])
    for key in ("last_run", "control", "panel", "pending_commands", "turns", "stop"):
        cl.user_session.set(key, None)  # đối tượng không lưu được thành JSON thì Chainlit trả về null hoặc [null, ...]
    saved = cl.user_session.get("settings") or {}
    widgets, _ = _widgets()
    for w in widgets:
        if w.id in saved and saved[w.id] is not None:
            if isinstance(w, Select) and saved[w.id] not in w.items:
                w.items[saved[w.id]] = saved[w.id]  # model đã chọn hôm đó nay không còn trong danh sách
            w.initial = saved[w.id]
    settings = await cl.ChatSettings(widgets).send()
    cl.user_session.set("settings", {**dict(settings), **saved})
    run = cl.user_session.get("run_ref") or {}
    actions = [cl.Action(name="run", payload={}, label="Chạy lượt mới")]
    if run.get("run_id") and (loaded := load_run(run["run_id"])):
        values, turns = loaded
        _set_unsaved("history_values", values)
        cl.user_session.set("turns", turns)
        status = values.get("final_status") or "chưa xong (đã dừng hoặc lỗi)"
        roles = [r for r in ("PM", "BA", "Backend", "Frontend", "Reviewer", "Tester") if turns.of(r)]
        actions = [_code_action()] + [cl.Action(name="show_role", payload={"role": r}, label=f"Chi tiết {r}")
                                      for r in roles] + actions
        text = (f"Đã mở lại lượt `{run['run_id']}` của **{_project_title(run.get('project', ''))}**, kết quả: "
                f"**{status}**. Hỏi Quản lý về lượt này, hoặc xem lại code và từng lượt của role bằng các nút dưới đây.")
    elif run.get("run_id"):
        text = f"Không còn dữ liệu đã lưu của lượt `{run['run_id']}`, chỉ xem lại được tin nhắn."
    else:
        text = "Cuộc chat này chưa chạy lượt nào."
    if (module := _module()) is not None:
        text = f"**Module: {module.title}** · " + text
        actions.append(cl.Action(name="module_edit", payload={}, label="Yêu cầu module", icon="file-pen"))
    # Chainlit gửi tin cũ cho giao diện (resume_thread) sau khi hàm này trả về, và lúc đó xóa nút của các tin gửi
    # trước. Nên gửi tin này từ một task riêng, sau khi hàm đã trả về.
    async def later():
        await asyncio.sleep(RESUME_DELAY)
        await cl.Message(content=text, actions=actions, metadata={"resume_notice": True}).send()

    asyncio.create_task(later())


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
    project = cl.user_session.get("project")
    if not project:
        await cl.Message(content="Chưa có dự án: lưu bản nháp ở khung bên phải trước, hoặc chọn một dự án ở ô trên cùng.").send()
        return
    mock = bool(settings.get("mock"))
    delay = float(settings.get("delay") or 0)
    models = {r: settings.get(f"model_{r}") or "mock" for r in ROLES}
    escalate = {r: v for r in ESCALATABLE if (v := settings.get(f"escalate_{r}")) and v != KEEP}
    module = cl.user_session.get("module")
    try:
        setup = prepare_run(project, (settings.get("requirements") or "").strip() or None,
                            models=models, escalate=escalate, mock=mock, module=module)
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
        cl.user_session.set("run_ref", {"run_id": setup.run_id, "project": setup.project.name, "module": module})
        _set_unsaved("history_values", {})
        title = setup.state.get("module_title") or setup.project.title
        await _name_thread(f"{title} · {setup.run_id}")
        try:
            await _run(setup, mock=mock, delay=delay)
        finally:
            cl.user_session.set("stop", None)  # hết lượt: bấm dừng lúc này không còn gì để dừng
            cl.user_session.set("control", None)
            if last := cl.user_session.get("last_run"):
                _save_run(last[1], last[0], cl.user_session.get("turns") or Turns())
            await _name_thread(f"{title} · {setup.run_id}")


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
    module = setup.state.get("module_title")
    moved = archive_output(out_dir, setup.run_id, keep=bool(module))
    if module:
        note = (f"\n\nModule **{module}**: team làm tiếp trên code đang có"
                + (f", bản trước lưu ở `{display(moved)}`." if moved else " (dự án chưa có code)."))
    else:
        note = f"\n\nĐầu ra lượt trước đã chuyển sang `{display(moved)}`." if moved else ""
    await cl.Message(content=f"Bắt đầu lượt `{setup.run_id}` · {format_models(setup, code=True)}{note}",
                     actions=[_code_action()]).send()

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
            if files:
                await _refresh_code()
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
                await cl.Message(content=summary_text(final, setup, time.monotonic() - started),
                                 actions=[_code_action()]).send()
            elif stop.is_set() and final_status != "Lỗi":
                final_status = "Đã dừng"
                await cl.Message(content="Đã dừng sau bước đang chạy.").send()
            elif stop.is_set():
                final_status = "Đã dừng"
            await _send_tasks(task_list, progress, final_status)
            break
