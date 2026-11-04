"""Lưu lịch sử chat và kết quả từng lượt chạy để mở lại sau (thanh bên trái của Chainlit).

- Lịch sử chat: Chainlit ghi tin nhắn vào SQLite `.chainlit/history.db` qua SQLiteDataLayer. Chainlit chỉ hiện danh
  sách cuộc chat khi có đăng nhập, nên tài khoản đọc từ UI_USERNAME / UI_PASSWORD trong .env.
- Kết quả lượt chạy: state cuối của graph và các lượt của từng role (khung Chi tiết) ghi vào runs/<run_id>.ui.json.
  Mở lại cuộc chat cũ thì đọc file này, nên Quản lý vẫn trả lời được về lượt đó và nút Chi tiết vẫn có dữ liệu.

Phần đọc/ghi file và bảng không phụ thuộc Chainlit (có test); lớp SQLiteDataLayer chỉ tạo khi app chạy.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import asdict
from pathlib import Path

from ui.turns import DiffLine, FileChange, Turn, Turns

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".chainlit" / "history.db"
SECRET_PATH = ROOT / ".chainlit" / "auth_secret"
RUNS_DIR = ROOT / "runs"
DEFAULT_USER = "admin"

# Bảng theo tài liệu Chainlit (bản Postgres), đổi kiểu cho SQLite. Cột JSON lưu dạng chuỗi.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    "id" TEXT PRIMARY KEY, "identifier" TEXT NOT NULL UNIQUE, "metadata" TEXT NOT NULL, "createdAt" TEXT);
CREATE TABLE IF NOT EXISTS threads (
    "id" TEXT PRIMARY KEY, "createdAt" TEXT, "name" TEXT, "userId" TEXT, "userIdentifier" TEXT, "tags" TEXT,
    "metadata" TEXT, FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS steps (
    "id" TEXT PRIMARY KEY, "name" TEXT NOT NULL, "type" TEXT NOT NULL, "threadId" TEXT NOT NULL, "parentId" TEXT,
    "streaming" BOOLEAN NOT NULL, "waitForAnswer" BOOLEAN, "isError" BOOLEAN, "metadata" TEXT, "tags" TEXT,
    "input" TEXT, "output" TEXT, "createdAt" TEXT, "command" TEXT, "start" TEXT, "end" TEXT, "generation" TEXT,
    "showInput" TEXT, "language" TEXT, "indent" INT, "defaultOpen" BOOLEAN, "autoCollapse" BOOLEAN,
    "modes" TEXT, "icon" TEXT, FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS elements (
    "id" TEXT PRIMARY KEY, "threadId" TEXT, "type" TEXT, "url" TEXT, "chainlitKey" TEXT, "name" TEXT NOT NULL,
    "display" TEXT, "objectKey" TEXT, "size" TEXT, "page" INT, "language" TEXT, "forId" TEXT, "mime" TEXT,
    "props" TEXT, "autoPlay" BOOLEAN, "playerConfig" TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS feedbacks (
    "id" TEXT PRIMARY KEY, "forId" TEXT NOT NULL, "threadId" TEXT NOT NULL, "value" INT NOT NULL, "comment" TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE);
"""
# Cột JSON: SQLite trả về chuỗi, giao diện Chainlit cần dict/list
JSON_KEYS = {"metadata", "generation", "tags", "modes", "props", "thread_metadata", "thread_tags",
             "step_metadata", "step_tags", "step_generation"}


def ensure_schema(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)


def auth_secret(path: Path = SECRET_PATH) -> str:
    """CHAINLIT_AUTH_SECRET trong .env, không có thì tạo một lần và giữ trong .chainlit/auth_secret (gitignore).
    Đổi khóa này thì mọi người phải đăng nhập lại."""
    if value := os.getenv("CHAINLIT_AUTH_SECRET"):
        return value
    if path.is_file() and (value := path.read_text(encoding="utf-8").strip()):
        return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value


def credentials() -> tuple[str, str, bool]:
    """(tài khoản, mật khẩu, đang dùng mật khẩu mặc định). Mặc định admin/admin để chạy được ngay trên máy mình."""
    user = os.getenv("UI_USERNAME") or DEFAULT_USER
    password = os.getenv("UI_PASSWORD")
    return user, password or DEFAULT_USER, not password


def check_login(username: str, password: str) -> bool:
    user, pw, _ = credentials()
    return hmac.compare_digest(username.encode(), user.encode()) and hmac.compare_digest(password.encode(), pw.encode())


def encode_params(params: dict) -> dict:
    """SQLite không nhận list/dict làm tham số: đổi sang chuỗi JSON."""
    return {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in params.items()}


def decode_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k in JSON_KEYS and isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
        out[k] = v
    return out


# ---------- kết quả lượt chạy ----------

def run_file(run_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / f"{run_id}.ui.json"


def save_run(run_id: str, values: dict, turns: Turns, *, project: str, runs_dir: Path = RUNS_DIR) -> Path:
    """Ghi state cuối và các lượt của từng role; gọi khi lượt chạy kết thúc (xong, lỗi hay dừng)."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = run_file(run_id, runs_dir)
    data = {"run_id": run_id, "project": project, "values": values,
            "turns": [asdict(t) for t in turns.all]}
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _turn(d: dict) -> Turn:
    files = [FileChange(**{**f, "lines": [DiffLine(**ln) for ln in f.get("lines", [])]}) for f in d.get("files", [])]
    t = Turn(**{**d, "files": files})
    if t.status == "running":  # lượt bị cắt ngang khi tắt app: không còn chạy nữa
        t.status = "failed"
    return t


def load_run(run_id: str, runs_dir: Path = RUNS_DIR) -> tuple[dict, Turns] | None:
    """(state, các lượt) của một lượt đã lưu, None nếu không có file hoặc file hỏng."""
    path = run_file(run_id, runs_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        turns = Turns()
        turns.all = [_turn(d) for d in data.get("turns", [])]
        return data.get("values") or {}, turns
    except (OSError, ValueError, TypeError):
        return None


def make_data_layer(db_path: Path = DB_PATH):
    """SQLAlchemyDataLayer của Chainlit cho SQLite: đổi tham số list/dict sang JSON và đọc JSON ra lại."""
    from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

    class SQLiteDataLayer(SQLAlchemyDataLayer):
        async def execute_sql(self, query: str, parameters: dict):
            result = await super().execute_sql(query, encode_params(parameters))
            if isinstance(result, list):
                return [decode_row(r) for r in result]
            return result

    ensure_schema(db_path)
    return SQLiteDataLayer(conninfo=f"sqlite+aiosqlite:///{db_path.as_posix()}")
