# M15 – Hỏi đáp nâng cao · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F09](../../features/F09-phan-tich-cau-hoi.md), [F14](../../features/F14-sinh-tra-loi-kiem-tra-trich-dan.md), [F08](../../features/F08-hoi-dap-chat.md)

## Chuẩn bị

- [ ] M13, M14 xong; golden Q1–Q5 chạy được ở chế độ non-stream
- [ ] Đo độ trễ `query_analysis` thực tế trên máy dev

## Triển khai – F09 LLM + hội thoại

- [ ] M15-T1 `query_analysis` no-think, temperature 0, JSON `LLMQueryOut`, timeout 1.5 s
- [ ] M15-T1 Đầu vào: câu hỏi, 3 lượt gần nhất, danh mục chủ đề / đối tượng
- [ ] M15-T1 Ánh xạ mờ danh mục ngưỡng 0.8; không ánh xạ được → bỏ
- [ ] M15-T1 LLM lỗi / quá hạn → ý định theo từ khóa, `llm_used = false`
- [ ] M15-T2 Quy tắc ghi đè LLM cho số hiệu / điều khoản / ngày; không trả số hiệu ngoài câu hỏi / lịch sử
- [ ] M15-T2 Câu nối tiếp kế thừa Điều + văn bản lượt trước
- [ ] M15-T2 Ngày áp dụng kế thừa lượt trước (`nguon_ngay = lich_su`)
- [ ] M15-T2 Định tuyến đủ `LOCAL` / `GLOBAL`; fallback DIRECT/GRAPH rỗng → `LOCAL`

## Triển khai – F14 đầy đủ

- [ ] M15-T3 V5 `HALLUCINATED_REF` (parse tham chiếu chữ, so ở cấp Điều trở xuống, gồm `unit_ids` ý tổng hợp và `nguon_sua_doi`)
- [ ] M15-T3 V6 `UNKNOWN_DOCUMENT`
- [ ] M15-T4 Sinh lại tối đa 2 lần với phản hồi lỗi cụ thể
- [ ] M15-T4 Hết lượt → xóa câu lỗi, `do_tin_cay = thap`, cảnh báo, nguồn đã xác minh
- [ ] M15-T4 Lưu `attempts`

## Triển khai – F08 SSE

- [ ] M15-T5 `stream=true` → SSE; `stream=false` giữ JSON như M09
- [ ] M15-T5 Sự kiện `analysis`, `progress`, `retrieval`, `token`, `replace`, `clarify`, `final` đúng thứ tự
- [ ] M15-T5 Keep-alive khi chờ Global map
- [ ] M15-T6 Quá 30 s → câu trả lời dự phòng
- [ ] M15-T6 LM Studio tắt giữa chừng → dự phòng hoặc `error LLM_UNAVAILABLE`, không treo
- [ ] M15-T6 Client ngắt → hủy lời gọi LLM, lưu trace `cancelled`

## Kiểm thử

- [ ] Unit hợp nhất quy tắc / LLM; ánh xạ mờ
- [ ] Tích hợp câu nối tiếp sau Q1
- [ ] Tích hợp LLM phân tích quá hạn
- [ ] Unit V5 (ví dụ F14 §5), V6
- [ ] Tích hợp sinh lại 1 lần / 3 lần đều sai
- [ ] SSE: thứ tự sự kiện (DIRECT, GLOBAL, CLARIFY); `<think>` cắt ngang không lộ; LM Studio tắt giữa stream
- [ ] M15-T7 Golden Q1–Q5 + câu nối tiếp qua stream

## Tiêu chí chấp nhận (F08 §7, F09 §7, F14 §7)

- [ ] Q1–Q5 đều trả lời được qua `POST /messages`, mỗi câu ≥ 1 trích dẫn
- [ ] Bảng route F09 §7: Q1 `DIRECT`, Q2 `LOCAL`, Q3 `GLOBAL`, Q4 `LOCAL` (ngày 2025-03-15), Q5 `GRAPH`
- [ ] "Còn khoản 2 thì sao?" sau Q1 → khoản 2 Điều 3 NĐ 123
- [ ] Không bao giờ trả số hiệu không có trong câu hỏi hoặc lịch sử
- [ ] Câu trả lời giả lập trích nhãn không tồn tại → `UNKNOWN_REF` và sinh lại
- [ ] Không có `<think>` trong bất kỳ `chat_message` nào
- [ ] P95 ≤ 10 s trên bộ câu hỏi (trừ Global)
- [ ] Tắt LM Studio giữa chừng → câu trả lời dự phòng hoặc 503 rõ ràng, không treo
- [ ] *(Đo ở M17)* Độ chính xác định tuyến ≥ 90%; độ chính xác trích dẫn ≥ 95%; trích dẫn hết hiệu lực ≤ 1%

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] M10 đợt 2 chạy được chat stream trên dữ liệu thật
