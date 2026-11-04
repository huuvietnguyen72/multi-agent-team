"""Chạy graph ở luồng nền và biến một lượt chạy thành dãy sự kiện đơn giản cho giao diện:
start (node bắt đầu), progress (bước bên trong node), done (node xong, kèm update), error (node lỗi), end (luôn có, kèm state cuối),
và khi có Quản lý: applied (đã áp một lệnh), rejected (lệnh không áp được), paused, resumed."""
from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Literal

RUN_LOCK = threading.Lock()  # OUTPUT_DIR là biến môi trường của cả tiến trình, nên mỗi lúc chỉ một lượt chạy


@dataclass(frozen=True)
class Event:
    kind: Literal["start", "progress", "done", "error", "end", "applied", "rejected", "paused", "resumed"]
    node: str | None = None
    update: dict | None = None   # chỉ có ở "done"
    message: str | None = None   # chỉ có ở "error"
    final: dict | None = None    # chỉ có ở "end"
    data: dict | None = None     # "start": state đưa vào node; "progress": {"node", "phase", ...} từ progress()
                                 # "applied"/"rejected": {"command"}; message = mô tả hoặc lý do


class RunControl:
    """Hàng chờ lệnh của Quản lý cho một lượt chạy. Giao diện gọi push(); stream_events() áp lệnh ở ranh giới
    giữa hai bước (mọi node của bước đã xong), vì update_state chỉ an toàn khi graph không còn node nào đang chạy."""

    def __init__(self, apply, validate=None):
        self._queue: queue.Queue = queue.Queue()
        self.wake = threading.Event()
        self.paused = False
        self.running: list[str] = []       # node đang chạy, cho Quản lý đọc
        self.apply = apply                 # (cmd, values, after_node) -> dict patch cho update_state
        self.validate = validate           # (cmd, values) -> lỗi | None

    def push(self, cmd) -> None:
        self._queue.put(cmd)
        self.wake.set()

    def pending(self) -> bool:
        return not self._queue.empty()

    def drain(self) -> list:
        out = []
        while not self._queue.empty():
            out.append(self._queue.get_nowait())
        return out


def stream_events(app, setup, stop: threading.Event | None = None, control: RunControl | None = None) -> Iterator[Event]:
    """Duyệt app.stream(..., stream_mode=["tasks", "updates", "custom", "checkpoints"]). `stop` đã set thì dừng khi
    bước đang chạy xong, vì không ngắt được một lần gọi model đang chạy.

    Có `control`: ở ranh giới giữa hai bước mà có lệnh chờ hoặc đang tạm dừng thì đóng stream, áp lệnh bằng
    app.update_state(config, patch, as_node=<node vừa xong>), rồi chạy tiếp bằng app.stream(None, config):
    LangGraph đọc lại checkpoint nên không làm lại bước cũ, và tính lại cạnh điều kiện từ node đó."""
    running: list[str] = control.running if control is not None else []
    inp, last_node = setup.state, None
    try:
        while True:
            reopen, step_done = False, False
            stream = app.stream(inp, setup.config, stream_mode=["tasks", "updates", "custom", "checkpoints"])
            try:
                for mode, chunk in stream:
                    if mode == "checkpoints":
                        # checkpoint của bước vừa xong đã lưu, bước sau chưa bắt đầu: chỗ duy nhất dừng hay sửa
                        # state an toàn (dừng ngay ở "updates" thì checkpoint có thể chưa ghi, mất update cuối)
                        if step_done and not running:
                            if stop is not None and stop.is_set():
                                break
                            if control is not None and (control.pending() or control.paused):
                                reopen = True
                                break
                        step_done = False
                        continue
                    if mode == "custom":
                        if isinstance(chunk, dict) and chunk.get("node"):
                            yield Event("progress", chunk["node"], data=dict(chunk))
                        continue
                    if mode == "tasks":
                        if "input" in chunk:  # task bắt đầu; task kết thúc có khóa "result", đã có ở updates
                            running.append(chunk["name"])
                            inp_ = chunk.get("input")
                            yield Event("start", chunk["name"], data=dict(inp_) if isinstance(inp_, dict) else {})
                        continue
                    for node, upd in (chunk or {}).items():
                        if node.startswith("__"):
                            continue
                        if node in running:
                            running.remove(node)
                        step_done, last_node = True, node
                        yield Event("done", node, update=upd or {})
            finally:
                stream.close()
            if not reopen:
                break
            yield from _apply_commands(app, setup, control, last_node, stop)
            if (stop is not None and stop.is_set()) or not app.get_state(setup.config).next:
                break
            inp = None
    except Exception as e:  # lỗi của một node: báo tên node đầu tiên đã bắt đầu mà chưa xong
        yield Event("error", node=running[0] if running else None, message=f"{type(e).__name__}: {e}")
    yield Event("end", final=dict(app.get_state(setup.config).values))


def _apply_commands(app, setup, control: RunControl, last_node: str, stop) -> Iterator[Event]:
    """Áp mọi lệnh đang chờ; đang tạm dừng thì chờ lệnh tiếp (resume, hoặc nút dừng của giao diện)."""
    announced = False
    while True:
        control.wake.clear()
        for cmd in control.drain():
            values = dict(app.get_state(setup.config).values)
            if cmd.action == "stop":
                control.paused = True
                continue
            if cmd.action == "resume":
                if control.paused:
                    control.paused = False
                    yield Event("resumed", last_node)
                continue
            error = control.validate(cmd, values) if control.validate else None
            if error:
                yield Event("rejected", last_node, message=error, data={"command": cmd})
                continue
            app.update_state(setup.config, control.apply(cmd, values, last_node), as_node=last_node)
            yield Event("applied", last_node, message=cmd.describe(), data={"command": cmd})
        if not control.paused or (stop is not None and stop.is_set()) or not app.get_state(setup.config).next:
            return  # graph đã hết bước thì không có gì để chờ
        if not announced:
            announced = True
            yield Event("paused", last_node)
        control.wake.wait(timeout=1.0)


@contextmanager
def exclusive_run() -> Iterator[bool]:
    """True nếu giành được lượt chạy, False nếu đang có lượt khác."""
    got = RUN_LOCK.acquire(blocking=False)
    try:
        yield got
    finally:
        if got:
            RUN_LOCK.release()
