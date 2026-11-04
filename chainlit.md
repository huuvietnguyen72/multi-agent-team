# Team AI agent

Giao diện theo dõi 6 agent (PM, BA, Backend, Frontend, Reviewer, Tester) làm một dự án trong `projects/`.

- Chọn dự án ở tin chào, đổi model từng role trong phần cài đặt (biểu tượng bánh răng cạnh ô nhập).
- Bật "Chạy thử (mock)" để xem cả luồng mà không tốn token.
- Bấm "Chi tiết" trên tin của một role để xem từng lượt và phần code đã sửa.
- Gõ vào khung chat để hỏi Quản lý (`Manager`) về lượt chạy, hoặc ra lệnh: "dừng lại", "chạy tiếp", "bỏ qua CR-xx", "dặn frontend: ...". Lệnh có hiệu lực khi bấm Đồng ý.
