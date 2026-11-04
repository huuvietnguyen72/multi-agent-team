## Backend

- Python 3.12, FastAPI, SQLite qua thư viện chuẩn `sqlite3` (file `todo.db`, tạo bảng khi khởi động).
- `path` của file tính từ thư mục backend: `app/main.py`, `app/...`, `tests/test_*.py`, `requirements.txt`.
- Test: pytest với `fastapi.testclient.TestClient`, dùng CSDL tạm cho mỗi test. Đặt tên test kèm mã BR, ví dụ `test_create_fourth_open_todo_rejected_br01`. Lệnh chạy: `python -m pytest -q`.
- Định dạng lỗi: HTTP 400 lỗi nghiệp vụ, 401 chưa đăng nhập, 403 không có quyền, 404 không tìm thấy; body `{"error": "<thông báo tiếng Việt>"}`.
- Đăng nhập đơn giản: `POST /api/login` trả `{userId}`; các request sau gửi header `X-User-Id`.
- Dữ liệu mẫu: hai tài khoản `an` / `123` và `binh` / `123`.
- Chạy: `uvicorn app.main:app --port 8000`, tiền tố API `/api`. Bật CORS cho frontend mở từ file tĩnh (chỉ dùng cho dev).

## Frontend

- HTML/CSS/JS thuần, không build: mở `index.html` là chạy.
- File: `index.html`, `app.js`, `style.css`. `const API_BASE = "http://localhost:8000/api"` ở đầu `app.js`.
- Gửi header `X-User-Id` sau khi đăng nhập; hiển thị lỗi từ trường `error` của body.

## Ngôn ngữ

- Giao diện, thông báo lỗi và tài liệu bằng tiếng Việt; code, tên biến và định danh bằng tiếng Anh.
