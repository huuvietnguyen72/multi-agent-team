"""Chạy graph ở luồng nền và biến một lượt chạy thành dãy sự kiện đơn giản cho giao diện:
start (node bắt đầu), progress (bước bên trong node), done (node xong, kèm update), error (node lỗi), end (luôn có, kèm state cuối)."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Literal

RUN_LOCK = threading.Lock()  # OUTPUT_DIR là biến môi trường của cả tiến trình, nên mỗi lúc chỉ một lượt chạy


@dataclass(frozen=True)
class Event:
    kind: Literal["start", "progress", "done", "error", "end"]
    node: str | None = None
    update: dict | None = None   # chỉ có ở "done"
    message: str | None = None   # chỉ có ở "error"
    final: dict | None = None    # chỉ có ở "end"
    data: dict | None = None     # "start": state đưa vào node; "progress": {"node", "phase", ...} từ progress()


def stream_events(app, setup, stop: threading.Event | None = None) -> Iterator[Event]:
    """Duyệt app.stream(..., stream_mode=["tasks", "updates", "custom"]). `stop` đã set thì dừng sau "done" kế tiếp,
    vì không ngắt được một lần gọi model đang chạy."""
    running: list[str] = []
    try:
        for mode, chunk in app.stream(setup.state, setup.config, stream_mode=["tasks", "updates", "custom"]):
            if mode == "custom":
                if isinstance(chunk, dict) and chunk.get("node"):
                    yield Event("progress", chunk["node"], data=dict(chunk))
                continue
            if mode == "tasks":
                if "input" in chunk:  # task bắt đầu; task kết thúc có khóa "result", đã có ở updates
                    running.append(chunk["name"])
                    inp = chunk.get("input")
                    yield Event("start", chunk["name"], data=dict(inp) if isinstance(inp, dict) else {})
                continue
            done_any = False
            for node, upd in (chunk or {}).items():
                if node.startswith("__"):
                    continue
                if node in running:
                    running.remove(node)
                done_any = True
                yield Event("done", node, update=upd or {})
            if done_any and stop is not None and stop.is_set():
                break
    except Exception as e:  # lỗi của một node: báo tên node đầu tiên đã bắt đầu mà chưa xong
        yield Event("error", node=running[0] if running else None, message=f"{type(e).__name__}: {e}")
    yield Event("end", final=dict(app.get_state(setup.config).values))


@contextmanager
def exclusive_run() -> Iterator[bool]:
    """True nếu giành được lượt chạy, False nếu đang có lượt khác."""
    got = RUN_LOCK.acquire(blocking=False)
    try:
        yield got
    finally:
        if got:
            RUN_LOCK.release()
