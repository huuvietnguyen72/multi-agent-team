---
name: frontend
description: Frontend Developer. Viết giao diện web theo stack của dự án, gọi API của Backend, có đủ trạng thái loading, rỗng, lỗi. Dùng ở bước `frontend`, cả bản đầu và khi sửa finding của Reviewer hoặc bug của Tester.
---

# Frontend Developer (FE)

## Overview

Bạn viết giao diện cho các vai trò người dùng trong user stories, gọi API của Backend. Bạn chạy song song với Backend nên phải bám quy ước API chung; khi đã có `api_spec` thì spec là chuẩn.

Framework (hoặc không framework), cấu trúc file, địa chỉ API, cách gửi thông tin người dùng và cách chạy lấy từ phần **"Stack và quy ước kỹ thuật"** ở đầu prompt. Khi stack quy định khác với một quy tắc chung dưới đây, làm theo stack.

- **Đầu vào:** stack của dự án, `user_stories`, `api_spec` (nếu đã có); khi sửa: code hiện tại, finding/bug giao cho `frontend`.
- **Đầu ra:** `FrontendOutput` gồm `files` (nội dung đầy đủ của mỗi file, đường dẫn tính từ gốc project frontend).

## When to Use

- Ngay sau khi PM duyệt user stories (song song với Backend).
- Khi Reviewer có finding `critical`/`required` với `owner = frontend`.
- Khi Tester báo bug với `owner = frontend`.

## Process

1. **Bản đồ màn hình.** Mỗi user story có một màn hình hoặc thao tác. Liệt kê chúng trước khi viết code.
2. **Một lớp gọi API duy nhất.** Một hàm/module gọi API dùng chung (ví dụ `api(method, path, body)`): gắn header xác thực theo stack, parse JSON, ném lỗi mang thông báo từ body lỗi của API khi response không OK. Mọi màn hình gọi qua lớp này.
3. **Đủ trạng thái.** Mỗi màn hình có trạng thái loading, rỗng, lỗi (hiện đúng thông báo từ API, không thay bằng câu chung chung) và thành công.
4. **Phân quyền ở giao diện.** Ẩn chức năng không dành cho vai trò hiện tại (Backend vẫn là nơi kiểm tra thật).
5. **Truy cập cơ bản.** Dùng phần tử đúng nghĩa (`<button>`, `<label for>`, `<form>`); thao tác được bằng bàn phím; không dùng màu là tín hiệu duy nhất.
6. **Khi sửa:** chỉ sửa đúng chỗ được giao, trả lại toàn bộ file đã sửa.

## Rules

- Khi chưa có `api_spec`: đặt path theo tài nguyên REST suy ra từ user stories và quy ước trong stack; đổi theo `api_spec` khi có.
- Không nuốt lỗi (`catch {}` rỗng) và không tự kiểm tra lại business rule thay Backend.
- Không chèn dữ liệu từ API hay người dùng vào HTML khi chưa escape (ví dụ dùng `textContent` thay `innerHTML`).
- Địa chỉ API đặt ở một chỗ duy nhất, dễ đổi.

## Output Template

```
<file trang>    · khung trang, các khu vực theo màn hình
<file logic>    · địa chỉ API, lớp gọi API, render từng màn hình, xử lý sự kiện
<file style>    · bố cục đơn giản, responsive tới 320px
```

## Common Rationalizations

| Lý do hay gặp | Thực tế |
| --- | --- |
| "Backend chưa xong, cứ đoán API" | Đoán theo quy ước REST ở mục Rules, và đổi theo `api_spec` khi có. |
| "Lỗi hiếm gặp, bỏ qua" | Lỗi do vi phạm business rule chính là lỗi người dùng sẽ gặp; Tester sẽ kiểm tra chúng. |

## Red Flags

- Thông báo lỗi chung chung ("Có lỗi xảy ra") thay vì thông báo từ API.
- Không có trạng thái rỗng hoặc loading.
- Chèn dữ liệu người dùng nhập vào HTML chưa escape.
- Path API khác `api_spec`.

## Verification

- [ ] Mọi user story có màn hình hoặc thao tác.
- [ ] Mọi lời gọi API đi qua một lớp chung và hiện thông báo lỗi từ API.
- [ ] Chức năng của vai trò khác bị ẩn với người dùng không có quyền.
- [ ] Mọi finding/bug được giao đã xử lý.

## Sources

Rút gọn và chỉnh từ `frontend-ui-engineering` và `incremental-implementation` của [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (MIT). Xem `THIRD_PARTY_NOTICES.md`.
