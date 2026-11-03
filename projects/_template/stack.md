Nội dung file này được chèn vào đầu prompt của mọi agent dưới tiêu đề "Stack và quy ước kỹ thuật".
Skill của từng role chỉ giữ nguyên tắc chung (contract-first, test cho mọi BR, đủ trạng thái giao diện...);
mọi chi tiết kỹ thuật riêng của dự án ghi ở đây. Viết ngắn, cụ thể, dạng gạch đầu dòng.

## Backend

- Ngôn ngữ và framework: <ví dụ: Spring Boot 3 + Java 17 + Maven / FastAPI + Python 3.12 / Express + Node 22>.
- CSDL: <ví dụ: H2 in-memory / SQLite / PostgreSQL>.
- Cấu trúc thư mục và gốc project: <ví dụ: `pom.xml`, `src/main/java/com/example/app/...`>.
- Test: <framework test> ; lệnh chạy: <giống [tests].command trong project.toml>.
- Định dạng lỗi: <ví dụ: 400/403/404, body `{"error": "<thông báo>"}`>.
- Xác thực: <ví dụ: không cần / header `X-User-Id` / JWT>.
- Dữ liệu mẫu: <cần những gì để chạy thử mọi user story>.
- Địa chỉ chạy: <ví dụ: `http://localhost:8080`, tiền tố `/api`; CORS cho dev nếu frontend chạy origin khác>.

## Frontend

- Công nghệ: <ví dụ: HTML/CSS/JS thuần không build / React + Vite / Vue 3>.
- File hoặc cấu trúc thư mục: <ví dụ: `index.html`, `app.js`, `style.css`>.
- Địa chỉ API: <ví dụ: `const API_BASE = "http://localhost:8080/api"` ở đầu `app.js`>.

## Ngôn ngữ

- <ví dụ: giao diện và thông báo bằng tiếng Việt; code và định danh bằng tiếng Anh.>
