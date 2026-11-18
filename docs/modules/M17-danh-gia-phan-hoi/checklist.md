# M17 – Đánh giá & phản hồi · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F16](../../features/F16-danh-gia-phan-hoi.md)

## Chuẩn bị (bắt đầu từ tuần 5)

- [ ] M17-T1 Bộ `eval_sets/mvp_v1.yaml` ≥ 50 câu, đủ trường BR-16.1
- [ ] M17-T1 Phủ 5 kiểu Q1–Q5 (≥ 8 câu mỗi kiểu) và 2 lĩnh vực (≥ 20 câu mỗi lĩnh vực)
- [ ] M17-T1 ≥ 30% câu thời điểm quá khứ / quy định đã bãi bỏ, có `trich_dan_cam`
- [ ] M17-T1 10 câu `holdout`
- [ ] M17-T1 Chuyên gia đã rà soát (ghi thời gian)

## Triển khai

- [ ] M17-T2 Migration `eval_question`, `eval_run`, `eval_result`, `feedback`
- [ ] M17-T2 CRUD câu hỏi, sửa tạo phiên bản mới, ngưng dùng (`active = false`), import YAML
- [ ] M17-T3 Runner chạy `pipeline.answer(stream=false)` trong phiên riêng; lưu `config_snapshot`
- [ ] M17-T3 Kiểm: trích dẫn hết hiệu lực (F13), trích dẫn cấm, precision / recall cấp Điều trở xuống, route
- [ ] M17-T3 Câu lỗi / timeout → `error`, tính sai, tiếp tục
- [ ] M17-T4 Judge từng ý chính (no-think, temperature 0); đúng khi ≥ 80% ý chính và không trích cấm / hết hiệu lực
- [ ] M17-T4 `PATCH /eval/results/{id}` ghi đè chuyên gia, được ưu tiên khi tính chỉ số
- [ ] M17-T5 Chỉ số đủ bảng F16 §1.2; so lượt trước; `regression` + thông báo
- [ ] M17-T6 Mẫu 50 cạnh đã duyệt cho chuyên gia; `edge_accuracy` + tỷ lệ edit / reject
- [ ] M17-T7 `POST /chat/messages/{id}/feedback` (6 lý do, sửa được)
- [ ] M17-T7 `GET /feedback/queue` ưu tiên `quy_dinh_het_hieu_luc`; `POST /feedback/{id}/triage` 3 hành động
- [ ] M17-T7 `to_eval` tạo câu hỏi `nguon = phan_hoi` điền sẵn
- [ ] Đủ endpoint F16 §5 (`/eval/questions*`, `/eval/runs*`, `/eval/results/{id}`)
- [ ] M17-T8 Handler `evaluate` nối vào M16; chạy lượt baseline

## Kiểm thử

- [ ] Unit so khớp cấp Điều, precision / recall ca biên
- [ ] Tích hợp chèn trích dẫn TT 78/2021 cho ngày 2026
- [ ] Tích hợp regression
- [ ] Tích hợp ghi đè chuyên gia
- [ ] Tích hợp 👎 → câu hỏi chuẩn
- [ ] Hiệu chỉnh judge: chuyên gia chấm lại 20%, ghi độ đồng thuận

## Tiêu chí chấp nhận (F16 §7)

- [ ] Có bộ ≥ 50 câu hỏi chuẩn trước khi kết thúc MVP
- [ ] Một lượt đánh giá báo đủ chỉ số bảng 1.2 và so sánh với lượt trước
- [ ] Chèn cố ý câu trả lời trích TT 78/2021 cho ngày 2026 → `expired_citation_rate > 0` được phát hiện
- [ ] Phản hồi 👎 chuyển được thành câu hỏi chuẩn trong ≤ 3 thao tác

## KPI mốc MVP (inception §7) – ghi kết quả lượt cuối

- [ ] Độ chính xác câu trả lời ≥ 85% (kết quả: ___)
- [ ] Tỷ lệ trích dẫn hết hiệu lực ≤ 1% (kết quả: ___)
- [ ] Độ chính xác trích dẫn ≥ 95% (kết quả: ___)
- [ ] Độ chính xác cạnh sửa đổi / bãi bỏ ≥ 99% (kết quả: ___)
- [ ] P95 thời gian phản hồi ≤ 10 s (kết quả: ___)
- [ ] Độ chính xác định tuyến ≥ 90% (kết quả: ___)

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Báo cáo lượt baseline lưu trong `docs/reports/`
