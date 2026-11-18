# M10 – Web chat & màn hình văn bản · Checklist

Plan: [implement-plan.md](implement-plan.md)

## Đợt 1 – PoC

### Chuẩn bị

- [ ] M09 xong; `POST /messages` (`stream=false`) trả `AnswerResponse` đúng F08 §5
- [ ] Chốt bộ UI (Tailwind + Radix hoặc thay thế)

### Triển khai

- [ ] M10-T1 Layout, routing, menu theo vai trò, trang cài đặt API key
- [ ] M10-T1 Sinh type TS từ OpenAPI (script + bước CI)
- [ ] M10-T2 Sidebar phiên: tạo, đổi tên, xóa, mở lại
- [ ] M10-T2 Ô nhập ≤ 1000 ký tự, bộ chọn ngày áp dụng
- [ ] M10-T2 Hiển thị `clarify` dạng nút lựa chọn
- [ ] M10-T2 Thông báo lỗi 409 (phiên đang xử lý), 429, 503
- [ ] M10-T3 Markdown + chú thích `[Cx]` bấm được
- [ ] M10-T3 Dòng "Ngày áp dụng", cảnh báo ngày mơ hồ
- [ ] M10-T3 Khối Nguồn có huy hiệu trạng thái; khối Lưu ý (notice)
- [ ] M10-T3 Bảng `structured_result`; banner `do_tin_cay = thap`; disclaimer luôn hiện
- [ ] M10-T4 Trang văn bản: metadata + trạng thái tại ngày, cây tô màu, quan hệ đi / đến
- [ ] M10-T4 Dòng thời gian phiên bản + nội dung từng phiên bản + sự kiện
- [ ] M10-T4 Mở từ trích dẫn (`?ngay=&unit=`) cuộn tới đúng điều khoản

### Kiểm thử

- [ ] Component `AnswerMessage`, `EffectivityBadge`, `VersionTimeline`
- [ ] Kịch bản demo Q1 (hôm nay và 15/3/2025), Q5

### Tiêu chí chấp nhận đợt 1

- [ ] Demo Q1, Q5 trên web với ~10–20 văn bản hóa đơn điện tử, không cần dùng API trực tiếp
- [ ] Mọi trích dẫn hiển thị khoảng hiệu lực và trạng thái

## Đợt 2 – MVP

### Triển khai

- [ ] M10-T5 Chat stream qua `fetch-event-source`: `analysis`, `retrieval`, `progress`, `token`, `replace`, `clarify`, `final`, lỗi
- [ ] M10-T5 Nút dừng câu hỏi (AbortController)
- [ ] M10-T6 👍 / 👎 + form lý do; sửa phản hồi
- [ ] M10-T6 Trang phân loại phản hồi (ưu tiên `quy_dinh_het_hieu_luc`, xem trace, 3 hành động)
- [ ] M10-T7 Trang chủ đề + trang tìm kiếm Local Search
- [ ] M10-T8 Trang câu hỏi chuẩn (CRUD, phiên bản), lượt đánh giá, kết quả, ghi đè chấm
- [ ] M10-T9 Trang quản trị: LLM, pipeline (chạy lại job lỗi, bật / tắt lịch), độ trễ cập nhật, chỉ mục, KPI
- [ ] Hoàn thiện trang duyệt (thống kê theo tuần, lọc theo rule)

### Kiểm thử

- [ ] Component SSE: `token` → `replace` → `token` → `final`
- [ ] Kịch bản demo Q1–Q5 bằng chat stream
- [ ] Kịch bản 👎 → tạo câu hỏi chuẩn trong ≤ 3 thao tác (F16 §7)

### Tiêu chí chấp nhận đợt 2

- [ ] Demo Q1–Q5 trên web với stream
- [ ] Không bao giờ hiển thị nội dung `<think>`
- [ ] Mọi chức năng biên tập / quản trị của F05, F15, F16, F17 dùng được qua giao diện

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] `npm run build` và test component chạy trong CI
