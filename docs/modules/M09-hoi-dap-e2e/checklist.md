# M09 – Hỏi đáp end-to-end (không stream) · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F09](../../features/F09-phan-tich-cau-hoi.md), [F14](../../features/F14-sinh-tra-loi-kiem-tra-trich-dan.md), [F08](../../features/F08-hoi-dap-chat.md)

## Chuẩn bị

- [ ] Văn bản PoC `INDEXED`; M07 + M08 xong (kể cả M07-T7)
- [ ] LM Studio chạy được `chat_answer` qua gateway

## Triển khai – phân tích câu hỏi (F09, quy tắc)

- [ ] M09-T1 Số hiệu đầy đủ khớp `VanBan.so_hieu`
- [ ] M09-T1 Số hiệu rút gọn qua fulltext `vanban_alias`; nhiều kết quả → `CLARIFY` + lựa chọn
- [ ] M09-T1 Điều khoản dùng `legal/refs.parse_refs`; thiếu văn bản → lấy từ lịch sử → `CLARIFY`
- [ ] M09-T1 Ngày cụ thể (3 dạng), ngày mơ hồ (tháng, năm) có `ngay_mo_ho`, mặc định hôm nay
- [ ] M09-T2 Ý định theo từ khóa; định tuyến BR-09.10 → 09.14; fallback DIRECT/GRAPH rỗng → LOCAL (`fallback_from`)
- [ ] M09-T2 Không trả số hiệu ngoài câu hỏi / lịch sử; số hiệu không có trong đồ thị → `van_ban_khong_co`
- [ ] M09-T2 `POST /query/analyze`, `GET /documents/resolve`

## Triển khai – sinh & kiểm tra (F14, cơ bản)

- [ ] M09-T3 Nhãn `[Cx]`, `[Nx]`; prompt đủ 7 quy tắc BR-14.3; `structured_result` dạng bảng
- [ ] M09-T3 Gọi `complete_text("chat_answer")`, `max_tokens 1024`; `ContextTooLong` → bớt ngữ cảnh
- [ ] M09-T4 V1 `UNKNOWN_REF`, V2 `EXPIRED_CITATION`, V3 `NOTICE_AS_CURRENT`, V4 `NO_CITATION`
- [ ] M09-T4 Không đạt → xóa câu lỗi, `do_tin_cay = thap`, cảnh báo
- [ ] M09-T4 Nhãn → `Citation` đầy đủ; luôn có disclaimer
- [ ] M09-T4 Ngữ cảnh + notice rỗng → câu cố định, không gọi LLM
- [ ] M09-T4 `POST /answer/generate`, `POST /answer/verify`

## Triển khai – chat (F08, không stream)

- [ ] M09-T5 Migration `chat_session`, `chat_message`, `message_citation`, `query_trace`
- [ ] M09-T5 Giới hạn: ≤ 1000 ký tự (422), 20 câu/phút/key (429), 1 câu đang xử lý/phiên (409)
- [ ] M09-T6 Pipeline F09 → DIRECT / GRAPH / BM25 tạm → **F13 filter** → F14
- [ ] M09-T6 Ngày áp dụng: UI > câu hỏi > lượt trước > hôm nay; luôn hiển thị trong câu trả lời
- [ ] M09-T6 `REFUSE` lịch sự + gợi ý tham vấn chuyên gia; `CLARIFY` trả lựa chọn
- [ ] M09-T6 Quá 30 s / LLM lỗi → câu trả lời dự phòng
- [ ] M09-T6 `mark_interactive()` khi bắt đầu lượt
- [ ] M09-T6 Sessions CRUD (xóa mềm), `POST /messages` (`stream=false`), `GET /chat/messages/{id}/trace`
- [ ] M09-T6 Lưu `latency_ms` từng bước; `raw_output` chỉ khi `TRACE_THINKING`

## Kiểm thử

- [ ] Unit rules (số hiệu, điều khoản, 6 dạng ngày)
- [ ] Unit routing (DIRECT, GRAPH, REFUSE, CLARIFY)
- [ ] Unit verifier (V1, V3, V4 với câu trả lời giả)
- [ ] Unit tách câu không cắt trong số hiệu / "Điều 3."
- [ ] Tích hợp LM Studio tắt → dự phòng, không treo
- [ ] Tích hợp 429 / 409
- [ ] M09-T7 Golden Q1, Q1-past, Q5, I53 (mock trong CI, LM Studio thật khi demo)

## Tiêu chí chấp nhận (phần PoC của F08, F09, F14)

- [ ] Q1 và Q5 trả lời được qua `POST /messages`, mỗi câu ≥ 1 trích dẫn
- [ ] Q1 → route `DIRECT`, điều khoản `123/2020/NĐ-CP:Đ3:K10`, ngày = hôm nay
- [ ] Q5 → route `GRAPH`, văn bản `70/2025/NĐ-CP`, `123/2020/NĐ-CP`
- [ ] Ví dụ inception §5.3 → nói rõ khoản 10 Điều 3 đã bị bãi bỏ từ 01/6/2025 và dẫn Điều 19 NĐ 123 (đã sửa đổi)
- [ ] Câu trả lời giả lập trích nhãn không tồn tại → bị phát hiện `UNKNOWN_REF`
- [ ] Không có `<think>` trong bất kỳ `chat_message` nào
- [ ] Tắt LM Studio giữa chừng → câu trả lời dự phòng hoặc 503 rõ ràng, không treo

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] `scripts/golden.py` chạy được và in bảng kết quả
