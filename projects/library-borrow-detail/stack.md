## Backend

- Spring Boot 3, Java 17, Maven, Spring Web, Spring Data JPA, H2 in-memory.
- Package gốc `com.example.library`. `path` của file tính từ gốc project Maven: `pom.xml`, `src/main/java/...`, `src/test/java/...`.
- Test: JUnit 5 (spring-boot-starter-test), gồm unit test cho service và test API bằng MockMvc. Đặt tên test kèm mã BR. Lệnh chạy: `mvn -q -B test`.
- Định dạng lỗi: 400 dữ liệu không hợp lệ, 403 không có quyền, 404 không tìm thấy; body `{"error": "<thông báo tiếng Việt>"}`.
- Không làm đăng nhập: sinh viên hiện tại lấy từ header `X-Student-Id` (theo requirements).
- "Hôm nay" lấy qua một bean `Clock` để test cố định được ngày.
- Server chạy ở `http://localhost:8080`, tiền tố API `/api`. Bật CORS cho frontend (chỉ dùng cho dev).

## Frontend

- HTML/CSS/JS thuần, không framework, không build.
- File: `index.html`, `app.js`, `style.css`. `const API_BASE = "http://localhost:8080/api"` ở đầu `app.js`.
- Trang chi tiết nhận `?id=<mã phiếu mượn>`; gửi header `X-Student-Id`.

## Ngôn ngữ

- Giao diện, thông báo lỗi và tài liệu bằng tiếng Việt; code, tên biến và định danh bằng tiếng Anh.
