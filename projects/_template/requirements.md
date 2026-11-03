# <Tên hệ thống>

## Mô tả
<Hệ thống làm gì, cho ai, trong 1-2 câu.>

## Người dùng
- <Vai trò 1>
- <Vai trò 2>

## Chức năng

Mỗi chức năng một mã F; BA sẽ viết ít nhất một user story cho mỗi mã.

| Mã | Chức năng | Người dùng |
| --- | --- | --- |
| F1 | <chức năng> | <vai trò> |
| F2 | <chức năng> | <vai trò> |

## Business rules

Mỗi quy tắc một mã BR, viết đo được (con số, giới hạn) và kèm đúng thông báo lỗi mong muốn.
BA biến mỗi BR thành acceptance criteria, Backend viết test, Reviewer và Tester đối chiếu theo mã này.

| Mã | Quy tắc |
| --- | --- |
| BR-01 | <quy tắc>; vi phạm thì lỗi 400 "<thông báo>" |
| BR-02 | <quy tắc> |

## Ràng buộc kỹ thuật
- Xem `stack.md`. Ghi ở đây những ràng buộc thuộc về đề bài (ví dụ: "không cần đăng nhập", "không cần deploy").

## Ví dụ kiểm thử mong đợi
- <Một tình huống cụ thể và kết quả đúng, để Tester và Reviewer đối chiếu.>
