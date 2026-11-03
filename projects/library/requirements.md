# Hệ thống mượn sách thư viện

## Mô tả
Web cho sinh viên tìm và mượn sách; thủ thư quản lý sách và xác nhận trả.

## Người dùng
- Sinh viên
- Thủ thư

## Chức năng

| Mã | Chức năng | Người dùng |
| --- | --- | --- |
| F1 | Đăng nhập bằng mã sinh viên / tài khoản thủ thư | Cả hai |
| F2 | Tìm sách theo tên, tác giả, thể loại | Sinh viên |
| F3 | Mượn sách còn trong kho | Sinh viên |
| F4 | Xem danh sách sách đang mượn và hạn trả | Sinh viên |
| F5 | Xác nhận trả sách | Thủ thư |
| F6 | Thêm, sửa, xóa sách | Thủ thư |

## Business rules

| Mã | Quy tắc |
| --- | --- |
| BR-01 | Mỗi sinh viên mượn tối đa 3 cuốn cùng lúc |
| BR-02 | Hạn trả là 14 ngày kể từ ngày mượn |
| BR-03 | Sinh viên có sách quá hạn thì không được mượn thêm |
| BR-04 | Không mượn được sách có số lượng tồn bằng 0 |
| BR-05 | Không xóa được sách đang có người mượn |

## Ràng buộc kỹ thuật
- Backend: Spring Boot + REST, CSDL H2 (in-memory).
- Frontend: HTML/JS thuần, gọi REST API của backend.
- Không cần deploy.

## Ví dụ kiểm thử mong đợi
Sinh viên đang mượn 3 cuốn gọi `POST /api/borrow` lần thứ 4 thì nhận lỗi 400 "Vượt quá 3 cuốn".
