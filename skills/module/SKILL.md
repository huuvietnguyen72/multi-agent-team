---
name: module
description: Soạn yêu cầu cho một module của dự án đang có. Biến mô tả ngắn của người dùng thành file modules/<tên>.md để team làm tiếp trên code hiện có trong một lượt chạy riêng.
---

# Soạn module

Người dùng muốn thêm một phần mới (module) vào dự án đang có. Tin nhắn kèm requirements chung của dự án, danh sách module đã có, và mô tả của người dùng. Khi đã có bản nháp trước, tin nhắn kèm bản nháp đó và yêu cầu sửa: giữ nguyên phần không bị yêu cầu đổi. Người dùng sẽ xem và sửa trước khi lưu, nên ghi rõ giả định thay vì hỏi lại.

## requirements (nội dung file module)

Dùng đúng các mục sau, theo thứ tự:

1. `## Mục tiêu`: một hai câu, module này cho ai làm được gì.
2. `## Chức năng`: bảng `| Mã | Chức năng | Mô tả |`. Dùng lại mã F của requirements chung khi module làm đúng chức năng đó; chức năng mới thì đánh số tiếp sau mã lớn nhất đang có.
3. `## Business rules`: bảng `| Mã | Quy tắc | Khi vi phạm |`. Dùng lại mã BR của requirements chung khi áp dụng; quy tắc mới thì đánh số tiếp. Mỗi quy tắc đo được và kèm mã HTTP và thông báo lỗi tiếng Việt trong ngoặc kép.
4. `## Liên quan tới phần đã có`: API, bảng dữ liệu, màn hình của module trước mà module này dùng hoặc phải sửa. Chưa biết thì ghi giả định.
5. `## Ngoài phạm vi`: những gì để module sau.
6. `## Ví dụ kiểm thử mong đợi`: dữ liệu cụ thể và mã BR.

Phạm vi nhỏ đủ cho một lượt chạy: 1 đến 4 chức năng. Không lặp lại stack; stack của dự án đã có trong stack.md.

## Các trường khác

- `title`: tên ngắn của module, tiếng Việt (không ghi chữ "Module" ở đầu).
- `slug`: chữ thường không dấu, số, gạch nối.
- `reply`: một hai câu nói đã soạn gì và các giả định chính, tiếng Việt.

## Red Flags

- Đổi mã F hoặc BR đã có trong requirements chung.
- Module trùng gần hết với một module đã có.
- Quy tắc không có con số hay thông báo lỗi cụ thể.
