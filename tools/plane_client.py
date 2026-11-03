"""Bọc REST API của Plane (mục 6 trong spec).

Cấu hình qua biến môi trường (đặt trong .env, không ghi vào code):
  PLANE_API_KEY, PLANE_WORKSPACE_SLUG, PLANE_PROJECT_ID, PLANE_BASE_URL (mặc định https://api.plane.so)

Thiếu cấu hình thì chạy dry-run: chỉ in ra thao tác, graph vẫn chạy bình thường.
Mọi lỗi Plane đều bị bắt lại để không làm dừng graph.
"""
from __future__ import annotations

import html
import itertools
import os

import requests

STATES = ["Backlog", "Todo", "In Progress", "In Review", "Done"]
LABELS = ["PM", "BA", "BE", "FE", "QA"]


class PlaneClient:
    def __init__(self) -> None:
        self.key = os.getenv("PLANE_API_KEY")
        self.slug = os.getenv("PLANE_WORKSPACE_SLUG")
        self.project = os.getenv("PLANE_PROJECT_ID")
        base = os.getenv("PLANE_BASE_URL", "https://api.plane.so").rstrip("/")
        self.enabled = bool(self.key and self.slug and self.project)
        self.url = f"{base}/api/v1/workspaces/{self.slug}/projects/{self.project}"
        self._states: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self._fake_ids = itertools.count(1)

    # ---------- nội bộ ----------
    def _req(self, method: str, path: str, **kw):
        r = requests.request(method, f"{self.url}{path}", timeout=20,
                             headers={"X-API-Key": self.key, "Content-Type": "application/json"}, **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    def _load_meta(self) -> None:
        if self._states:
            return
        for s in self._req("GET", "/states/").get("results", []):
            self._states[s["name"].lower()] = s["id"]
        for lb in self._req("GET", "/labels/").get("results", []):
            self._labels[lb["name"].upper()] = lb["id"]

    def _safe(self, desc: str, fn, default=None):
        if not self.enabled:
            print(f"   [plane:dry-run] {desc}")
            return default
        try:
            self._load_meta()
            result = fn()
            print(f"   [plane] {desc}")
            return result
        except Exception as e:  # không để lỗi Plane làm dừng graph
            print(f"   [plane:lỗi] {desc}: {e}")
            return default

    # ---------- API mức cao cho agent ----------
    def create_task(self, title: str, label: str, state: str = "Backlog",
                    description: str = "", parent_id: str | None = None) -> str:
        fake = f"local-{next(self._fake_ids)}"

        def call():
            body = {"name": title, "description_html": f"<p>{html.escape(description)}</p>"}
            if (sid := self._states.get(state.lower())):
                body["state"] = sid
            if (lid := self._labels.get(label.upper())):
                body["labels"] = [lid]
            if parent_id and not parent_id.startswith("local-"):
                body["parent"] = parent_id
            return self._req("POST", "/issues/", json=body)["id"]

        return self._safe(f"tạo task [{label}] '{title}' ở {state}", call, default=fake) or fake

    def move_task(self, task_id: str | None, state: str) -> None:
        if not task_id:
            return

        def call():
            if task_id.startswith("local-"):
                return
            self._req("PATCH", f"/issues/{task_id}/", json={"state": self._states[state.lower()]})

        self._safe(f"chuyển {task_id} sang {state}", call)

    def add_comment(self, task_id: str | None, text: str) -> None:
        if not task_id:
            return

        def call():
            if task_id.startswith("local-"):
                return
            body = "<p>" + html.escape(text).replace("\n", "<br/>") + "</p>"
            self._req("POST", f"/issues/{task_id}/comments/", json={"comment_html": body})

        short = text if len(text) < 80 else text[:77] + "..."
        self._safe(f"comment lên {task_id}: {short}", call)


plane = PlaneClient()
