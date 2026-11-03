## Backend

- Spring Boot 3, Java 17, Maven, Spring Web, Spring Data JPA, H2 in-memory.
- Package gốc `com.example.library`. `path` của file tính từ gốc project Maven: `pom.xml`, `src/main/java/...`, `src/test/java/...`.
- Test: JUnit 5 (spring-boot-starter-test). Đặt tên test kèm mã BR, ví dụ `borrow_rejectsFourthBook_BR01`. Lệnh chạy: `mvn -q -B test`.
- Định dạng lỗi: HTTP 400 cho lỗi nghiệp vụ, 403 không có quyền, 404 không tìm thấy; body `{"error": "<thông báo tiếng Việt>"}`.
- Dữ liệu mẫu: vài sinh viên, một thủ thư, vài cuốn sách (`data.sql` hoặc `CommandLineRunner`).
- Đăng nhập đơn giản: `POST /api/login` trả `{userId, role}`; các request sau gửi header `X-User-Id`. Endpoint của thủ thư phải kiểm tra role.
- Server chạy ở `http://localhost:8080`, tiền tố API `/api`. Bật CORS cho frontend mở từ file tĩnh (chỉ dùng cho dev).

## Frontend

- HTML/CSS/JS thuần, không framework, không build: mở `index.html` là chạy.
- File: `index.html`, `app.js`, `style.css`. `const API_BASE = "http://localhost:8080/api"` ở đầu `app.js`.
- Gửi header `X-User-Id` sau khi đăng nhập; hiển thị lỗi từ trường `error` của body.
- Khi chưa có `api_spec`, dùng quy ước: `/api/login`, `/api/books`, `/api/borrow`, `/api/borrows/me`, `/api/borrows/{id}/return`.

## Ngôn ngữ

- Giao diện, thông báo lỗi và tài liệu bằng tiếng Việt; code, tên biến và định danh bằng tiếng Anh.
