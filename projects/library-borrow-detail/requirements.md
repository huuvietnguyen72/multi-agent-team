# Module: Xem chi tiết sách đang mượn

## Mô tả
Một module nhỏ của hệ thống mượn sách thư viện: sinh viên mở một phiếu mượn trong danh sách sách đang mượn để xem chi tiết cuốn sách và tình trạng hạn trả. Dùng để thử cả team agent trên phạm vi nhỏ.

## Người dùng
- Sinh viên

## Chức năng

| Mã | Chức năng | Người dùng |
| --- | --- | --- |
| F7 | Xem chi tiết một phiếu mượn của mình: tên sách, tác giả, thể loại, ngày mượn, hạn trả, số ngày còn lại hoặc số ngày quá hạn, trạng thái (ĐANG MƯỢN / QUÁ HẠN / ĐÃ TRẢ) | Sinh viên |

## Business rules

| Mã | Quy tắc |
| --- | --- |
| BR-02 | Hạn trả là 14 ngày kể từ ngày mượn |
| BR-06 | Sinh viên chỉ xem được phiếu mượn của chính mình; xem phiếu của người khác thì nhận lỗi 403 |
| BR-07 | Phiếu mượn không tồn tại thì nhận lỗi 404 |
| BR-08 | Quá hạn khi hôm nay sau hạn trả và sách chưa trả; khi đó hiển thị số ngày quá hạn thay cho số ngày còn lại |

## Ràng buộc kỹ thuật
- Backend: Spring Boot + REST, CSDL H2 (in-memory), có dữ liệu mẫu: 2 sinh viên, 3 phiếu mượn (1 đang mượn, 1 quá hạn, 1 đã trả).
- Không làm đăng nhập trong module này: sinh viên hiện tại lấy từ header `X-Student-Id`.
- Frontend: HTML/JS thuần, một trang chi tiết nhận `?id=<mã phiếu mượn>`, có trạng thái đang tải, lỗi 403, lỗi 404.
- Không cần deploy.

## Ví dụ kiểm thử mong đợi
- Sinh viên SV01 gọi `GET /api/borrows/{id}` với phiếu của SV02 thì nhận lỗi 403.
- Phiếu mượn ngày 2026-10-01, chưa trả, xem vào ngày 2026-10-20 thì hạn trả là 2026-10-15, trạng thái QUÁ HẠN, quá hạn 5 ngày.
