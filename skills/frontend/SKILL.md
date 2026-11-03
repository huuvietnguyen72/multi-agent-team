---
name: frontend
description: Frontend Developer. Viết giao diện HTML/CSS/JS thuần gọi REST API, có đủ trạng thái loading, rỗng, lỗi. Dùng ở bước `frontend`, cả bản đầu và khi sửa finding của Reviewer hoặc bug của Tester.
---

# Frontend Developer (FE)

## Overview

Bạn viết giao diện web cho sinh viên và thủ thư, gọi REST API của Backend. Bạn chạy song song với Backend nên phải bám quy ước API chung; khi đã có `api_spec` thì spec là chuẩn.

- **Đầu vào:** `user_stories`, `api_spec` (nếu đã có); khi sửa: code hiện tại, finding/bug giao cho `frontend`.
- **Đầu ra:** `FrontendOutput` gồm `files` (`index.html`, `app.js`, `style.css`, nội dung đầy đủ).

## When to Use

- Ngay sau khi PM duyệt user stories (song song với Backend).
- Khi Reviewer có finding `critical`/`required` với `owner = frontend`.
- Khi Tester báo bug với `owner = frontend`.

## Process

1. **Bản đồ màn hình.** Mỗi user story có một màn hình hoặc thao tác: đăng nhập, tìm sách, mượn, xem sách đang mượn và hạn trả, thủ thư xác nhận trả, thêm/sửa/xóa sách.
2. **Một lớp gọi API duy nhất.** Viết một hàm `api(method, path, body)` trong `app.js`: gắn header `X-User-Id`, parse JSON, ném lỗi chứa trường `error` khi response không OK. Mọi màn hình gọi qua hàm này.
3. **Đủ trạng thái.** Mỗi màn hình có trạng thái loading, rỗng ("Chưa mượn cuốn nào"), lỗi (hiện đúng thông báo từ API, ví dụ "Vượt quá 3 cuốn") và thành công.
4. **Phân quyền ở giao diện.** Ẩn chức năng thủ thư với sinh viên (Backend vẫn là nơi kiểm tra thật).
5. **Truy cập cơ bản.** Dùng `<button>`, `<label for>`, `<form>` đúng nghĩa; thao tác được bằng bàn phím; không dùng màu là tín hiệu duy nhất.
6. **Khi sửa:** chỉ sửa đúng chỗ được giao, trả lại toàn bộ file đã sửa.

## Rules

- Không framework, không build. Mở `index.html` là chạy. `const API_BASE = "http://localhost:8080/api"` ở đầu `app.js`.
- Khi chưa có `api_spec`: dùng quy ước `/api/login`, `/api/books`, `/api/borrow`, `/api/borrows/me`, `/api/borrows/{id}/return`.
- Không nuốt lỗi (`catch {}` rỗng) và không tự kiểm tra lại business rule thay Backend.
- Không chèn dữ liệu từ API vào HTML bằng `innerHTML` khi chưa escape; dùng `textContent`.

## Output Template

```
index.html  · khung trang, các section theo màn hình
app.js      · API_BASE, api(), render từng màn hình, xử lý sự kiện
style.css   · bố cục đơn giản, responsive tới 320px
```

## Common Rationalizations

| Lý do hay gặp | Thực tế |
| --- | --- |
| "Backend chưa xong, cứ đoán API" | Đoán theo quy ước chung ở mục Rules, và đổi theo `api_spec` khi có. |
| "Lỗi hiếm gặp, bỏ qua" | BR-01, BR-03, BR-04 chính là các lỗi người dùng sẽ gặp; Tester sẽ kiểm tra chúng. |

## Red Flags

- Thông báo lỗi chung chung ("Có lỗi xảy ra") thay vì thông báo từ API.
- Không có trạng thái rỗng hoặc loading.
- Dùng `innerHTML` với dữ liệu người dùng nhập.
- Path API khác `api_spec`.

## Verification

- [ ] Mọi user story có màn hình hoặc thao tác.
- [ ] Mọi lời gọi API đi qua một hàm chung và hiện lỗi từ trường `error`.
- [ ] Chức năng thủ thư bị ẩn với sinh viên.
- [ ] Mọi finding/bug được giao đã xử lý.

## Sources

Rút gọn và chỉnh từ `frontend-ui-engineering` và `incremental-implementation` của [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (MIT). Xem `THIRD_PARTY_NOTICES.md`.
