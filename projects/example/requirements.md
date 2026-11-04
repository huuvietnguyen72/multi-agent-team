# Danh sách việc cần làm

## Mô tả
Ứng dụng web nhỏ để mỗi người ghi lại các việc cần làm của mình. Dùng làm dự án mẫu để thử khung multi-agent.

## Người dùng
- Người dùng: có tài khoản, chỉ thấy và sửa việc của chính mình.

## Chức năng

| Mã | Chức năng | Người dùng |
| --- | --- | --- |
| F1 | Đăng nhập bằng tên đăng nhập và mật khẩu | Người dùng |
| F2 | Tạo việc mới (tên, hạn chót tùy chọn) | Người dùng |
| F3 | Xem danh sách việc của mình, việc chưa xong xếp trước | Người dùng |
| F4 | Đánh dấu một việc là đã xong | Người dùng |

## Business rules

| Mã | Quy tắc |
| --- | --- |
| BR-01 | Mỗi người có tối đa 3 việc chưa xong; tạo việc thứ 4 thì lỗi 400 "Vượt quá giới hạn 3 việc chưa xong" |
| BR-02 | Tên việc không được trống và dài tối đa 100 ký tự; sai thì lỗi 400 "Tên việc không hợp lệ" |
| BR-03 | Không xem hay sửa được việc của người khác; thử thì lỗi 403 "Không có quyền với việc này" |

## Ràng buộc kỹ thuật
- Xem `stack.md`. Không cần đăng ký tài khoản (dùng tài khoản mẫu), không cần deploy.

## Ví dụ kiểm thử mong đợi
- `an` đã có 3 việc chưa xong, tạo thêm "Đi chợ" thì nhận lỗi 400 "Vượt quá giới hạn 3 việc chưa xong"; đánh dấu xong một việc rồi tạo lại thì được.
- `binh` mở việc có id của `an` thì nhận lỗi 403 "Không có quyền với việc này".
