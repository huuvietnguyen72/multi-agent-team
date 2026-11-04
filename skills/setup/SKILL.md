---
name: setup
description: Soạn dự án mới cho team. Biến ý tưởng một vài câu của người dùng thành requirements.md và stack.md theo đúng mẫu của khung, để người dùng duyệt và sửa trước khi team chạy.
---

# Soạn dự án mới

Người dùng mô tả ý tưởng phần mềm bằng vài câu. Bạn soạn hai file mà team (PM, BA, Backend, Frontend, Reviewer, Tester) sẽ đọc. Người dùng sẽ xem và sửa trước khi lưu, nên ghi rõ giả định thay vì hỏi lại. Mỗi tin nhắn kèm hai file mẫu; khi đã có bản nháp trước, tin nhắn kèm bản nháp đó và yêu cầu sửa của người dùng: giữ nguyên phần không bị yêu cầu đổi.

## requirements.md

- Giữ đúng các mục của mẫu: Mô tả, Người dùng, Chức năng (bảng F1..Fn), Business rules (bảng BR-xx), Ràng buộc kỹ thuật, Ví dụ kiểm thử mong đợi.
- Phạm vi nhỏ đủ cho một lượt chạy: 3 đến 6 chức năng, 3 đến 6 business rule. Ý tưởng lớn thì chọn phần lõi và ghi phần còn lại vào "Ràng buộc kỹ thuật" là ngoài phạm vi.
- Mỗi BR đo được (con số, giới hạn, quyền) và kèm đúng mã HTTP và thông báo lỗi tiếng Việt trong ngoặc kép.
- Ví dụ kiểm thử dùng dữ liệu cụ thể (tên tài khoản mẫu, con số) và nhắc mã BR.

## stack.md

- Giữ đúng các mục của mẫu: Backend, Frontend, Ngôn ngữ.
- Người dùng không nói stack thì chọn thứ đơn giản chạy được ngay trên máy cá nhân: Python FastAPI + SQLite (`sqlite3`) + pytest cho backend, HTML/CSS/JS thuần không build cho frontend.
- Ghi cụ thể: cấu trúc thư mục và gốc của đường dẫn file, lệnh chạy test, định dạng lỗi `{"error": "..."}`, cách xác thực đơn giản, tài khoản mẫu, địa chỉ chạy và CORS cho dev, `API_BASE` ở đầu `app.js`.

## Các trường khác

- `title`: tên ngắn, tiếng Việt. `slug`: chữ thường không dấu, số, gạch nối.
- `test_command`: lệnh test của backend đúng với stack (ví dụ `python -m pytest -q` hoặc `npm test --silent`).
- `reply`: một hai câu nói đã soạn gì và các giả định chính, tiếng Việt.

## Red Flags

- Bỏ mục của mẫu hoặc đổi tên mục.
- BR không có con số hay thông báo lỗi cụ thể.
- Chọn stack cần dịch vụ ngoài (cloud, Docker, CSDL server) khi người dùng không yêu cầu.
