# M17 – Đánh giá & phản hồi · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F16 – Đánh giá chất lượng & phản hồi](../../features/F16-danh-gia-phan-hoi.md) |
| Giai đoạn | MVP – tuần 10 (soạn bộ câu hỏi bắt đầu từ tuần 5) |
| Ước lượng | 5 ngày code + thời gian soạn câu hỏi (song song) |
| Phụ thuộc | M15 (pipeline đầy đủ), M07 (`EffectivityService`), M01 (`judge`) |
| Module dùng kết quả | M16 (hồi quy sau cập nhật), M18 (báo cáo KPI) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Đo KPI inception §7 một cách tự động, lặp lại được, so sánh giữa các lượt; thu phản hồi 👍/👎 và biến phản hồi tiêu cực thành câu hỏi kiểm thử.

## 2. Thiết kế

### 2.1. Cấu trúc file

```text
backend/app/eval/
├── models.py          # ORM eval_question, eval_run, eval_result, feedback (F16 §6)
├── questions.py       # CRUD + phiên bản (BR-16.3), import / export YAML
├── runner.py          # handler job "evaluate" – UC-16.1
├── checks.py          # trích dẫn hết hiệu lực, trích dẫn cấm, precision / recall, route
├── judge.py           # LLM judge từng ý chính (BR-16.6)
├── metrics.py         # tổng hợp chỉ số, so lượt trước, regression (BR-16.5)
├── edge_audit.py      # mẫu 50 cạnh đã duyệt cho chuyên gia + tỷ lệ edit/reject (KPI cạnh)
├── feedback.py        # UC-16.3, UC-16.4, hàng đợi ưu tiên (BR-16.7 → 16.9)
└── router.py          # /eval/*, /chat/messages/{id}/feedback, /feedback/*
backend/eval_sets/
└── mvp_v1.yaml        # bộ câu hỏi chuẩn ban đầu (nhập vào DB bằng script)
```

### 2.2. Bộ câu hỏi chuẩn (BR-16.1, BR-16.2)

| Yêu cầu | Kế hoạch |
|---|---|
| ≥ 50 câu | Nhóm dev soạn nháp từ văn bản đã nạp (tuần 5–9), chuyên gia rà soát trong ngân sách 2 giờ/tuần |
| Phủ Q1–Q5 | ≥ 8 câu mỗi kiểu: DIRECT hiệu lực / nội dung / lịch sử, GRAPH, LOCAL, GLOBAL, REFUSE / CLARIFY |
| Hai lĩnh vực | ≥ 20 câu hóa đơn điện tử, ≥ 20 câu thuế hộ kinh doanh |
| ≥ 30% thời điểm quá khứ / quy định đã bãi bỏ | Tag `thoi_diem_qua_khu`, `da_bai_bo`; mỗi câu có `trich_dan_cam` là điều khoản hết hiệu lực tại ngày áp dụng |
| Mỗi câu | `cau_hoi`, `ngay_ap_dung`, `route_mong_doi`, `y_chinh[]` (phát biểu ngắn, kiểm chứng được), `trich_dan_mong_doi[]` (cấp Điều trở xuống), `trich_dan_cam[]`, `nhom`, `tags` |
| Lưu trữ | YAML trong repo (review được qua PR) → import vào `eval_question`; sửa trên giao diện tạo phiên bản mới |

### 2.3. Chạy đánh giá (UC-16.1)

```python
async def run_eval(run_id):
    snapshot = config_snapshot()   # model, tham số LLM, CHAT_THINKING, phiên bản code (git sha), số văn bản INDEXED, thời điểm index cuối
    for q in active_questions(filter):
        try:
            resp = await pipeline.answer(eval_session, q.cau_hoi, ngay_ui=q.ngay_ap_dung, stream=False)  # BR-16.4
        except Exception as e:
            save_result(q, error=str(e), judge_correct=False); continue               # ngoại lệ 3a
        cited = [c.unit_id for c in resp.citations if c.ref.startswith("C")]
        expired = [u for u, s in effectivity.check(cited, q.ngay_ap_dung) if s != CON_HIEU_LUC]
        forbidden = match_level(cited, q.trich_dan_cam)
        precision, recall = prf(cited, q.trich_dan_mong_doi)                               # so cấp Điều trở xuống
        judge = await judge_points(resp.answer, q.y_chinh)                                 # [{"y", "co"}]
        correct = ratio(judge) >= 0.8 and not forbidden and not expired
        save_result(...)
    compute_metrics(run_id); compare_previous(run_id)
```

| Chi tiết | Cách làm |
|---|---|
| Phiên riêng | `chat_session` với `api_key_id = 'eval'`, không hiện cho người dùng |
| So khớp cấp Điều trở xuống | Trích `…:Đ19:K1` khớp kỳ vọng `…:Đ19`; kỳ vọng `…:Đ19:K1` không khớp trích `…:Đ19:K2` |
| Judge | `complete_json("judge", …)` từng câu: đầu vào câu trả lời + danh sách ý chính, đầu ra `[{y, co: bool, ly_do}]`; temperature 0, no-think; nhãn "ước lượng tự động" |
| Chỉ số (F16 §1.2) | `accuracy`, `expired_citation_rate` (câu có ≥ 1 trích hết hiệu lực hoặc trích cấm / tổng), `citation_precision`, `citation_recall`, `routing_accuracy`, `latency_p95_ms`; ghi đè chuyên gia (`expert_correct`) được ưu tiên khi tính `accuracy` |
| So sánh (BR-16.5) | `previous_run_id` = lượt `DONE` gần nhất cùng `filter`; `regression = accuracy giảm > 0.05 hoặc expired_citation_rate > 0.01` → thông báo quản trị (bảng `notification` của M16) |
| Thời gian | 50 câu × ~10 s + judge → ~15 phút; chạy như job ưu tiên 3, nhường chat |

### 2.4. KPI cạnh sửa đổi / bãi bỏ

`edge_audit`: lấy mẫu ngẫu nhiên 50 ứng viên `da_duyet` (`SUA_DOI`/`BAI_BO`/`THAY_THE`) → trang chuyên gia đánh dấu đúng / sai (tái dùng màn duyệt, chế độ chỉ đọc) → `edge_accuracy`; kèm tỷ lệ `edit_approve` / `reject` từ `review_action`.

### 2.5. Phản hồi người dùng (BR-16.7 → 16.9)

- `POST /chat/messages/{id}/feedback`: `rating up/down`; `down` bắt buộc `ly_do` thuộc 6 giá trị; một phản hồi / (message, key), gửi lại = sửa (`UNIQUE` + upsert).
- Hàng đợi `GET /feedback/queue`: chỉ `down`, `triage = pending`, sắp `ly_do = quy_dinh_het_hieu_luc` trước, rồi mới nhất trước.
- `POST /feedback/{id}/triage {"action": "to_eval" | "data_issue" | "ignored", ...}`:
  - `to_eval`: tạo `eval_question` `nguon = phan_hoi` điền sẵn câu hỏi + ngày áp dụng của tin nhắn; biên tập viên bổ sung `y_chinh`, trích dẫn → lưu. Giao diện: (1) bấm "Tạo câu hỏi chuẩn" → (2) điền ý chính → (3) lưu = **3 thao tác** (F16 §7).
  - `data_issue`: ghi chú + link tới văn bản / ứng viên liên quan (từ trace).

### 2.6. Schema & API

Migration `eval_question`, `eval_run`, `eval_result`, `feedback` đúng F16 §6; API đúng F16 §5.

## 3. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M17-T1 | Soạn bộ câu hỏi `mvp_v1.yaml` | 2.2 – bắt đầu tuần 5, song song M11–M15 | 16.1, 16.2 | (song song) |
| M17-T2 | Migration + questions CRUD + phiên bản + import YAML | 2.6, 2.2 | 16.3 | 0.75 ngày |
| M17-T3 | Runner + checks | 2.3 | 16.4 | 1 ngày |
| M17-T4 | Judge + ghi đè chuyên gia | 2.3 | 16.6 | 0.75 ngày |
| M17-T5 | Metrics + so sánh + regression + thông báo | 2.3 | 16.5 | 0.5 ngày |
| M17-T6 | Edge audit | 2.4 | – | 0.5 ngày |
| M17-T7 | Feedback + triage | 2.5 | 16.7–16.9 | 0.75 ngày |
| M17-T8 | Nối hồi quy vào M16 (M16-T9) + lượt đánh giá baseline + báo cáo | – | 15.8 | 0.75 ngày |

## 4. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit `checks` | So khớp cấp Điều trở xuống; precision / recall trên ca biên (không trích dẫn, không kỳ vọng) |
| Tích hợp | Chèn cố ý một câu trả lời (mock pipeline) trích TT 78/2021 cho ngày 2026 → `expired_citation_rate > 0` (F16 §7) |
| Tích hợp | Hai lượt, lượt 2 giả lập giảm accuracy 0.1 → `regression = true` + thông báo |
| Tích hợp | Ghi đè chuyên gia đổi `accuracy` khi tính lại |
| Tích hợp | Câu lỗi (timeout) → `error`, tính là sai, lượt vẫn hoàn thành |
| Tích hợp | 👎 → hàng đợi (ưu tiên `quy_dinh_het_hieu_luc`) → `to_eval` tạo câu hỏi `nguon = phan_hoi` |
| Hiệu chỉnh judge | Chuyên gia chấm lại mẫu 20% lượt đầu; ghi tỷ lệ đồng thuận judge – chuyên gia |

## 5. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Qwen 9B làm judge không đáng tin | Ý chính viết ngắn, kiểm chứng được; chuyên gia chấm lại 20%; báo cáo độ đồng thuận; kết quả luôn ghi "ước lượng tự động" |
| Thiếu thời gian chuyên gia để soạn 50 câu | Dev soạn nháp đầy đủ trường, chuyên gia chỉ duyệt / sửa; ưu tiên câu thời điểm quá khứ và đã bãi bỏ |
| Bộ câu hỏi "học thuộc" (chỉnh prompt theo bộ đánh giá) | Giữ 10 câu làm tập ẩn (`tags: holdout`), chỉ chạy ở mốc MVP |

## 6. Bàn giao

- M18 dùng lượt đánh giá cuối làm báo cáo KPI mốc MVP.
- M16 gọi `evaluate` sau mỗi cập nhật có văn bản mới `INDEXED`.
