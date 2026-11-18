# M15 – Hỏi đáp nâng cao · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F09](../../features/F09-phan-tich-cau-hoi.md) (LLM + hội thoại), [F14](../../features/F14-sinh-tra-loi-kiem-tra-trich-dan.md) (V5, V6, sinh lại), [F08](../../features/F08-hoi-dap-chat.md) (SSE stream) |
| Giai đoạn | MVP – tuần 9 |
| Ước lượng | 5 ngày |
| Phụ thuộc | M09, M13, M14 |
| Module dùng kết quả | M10 đợt 2, M17 |
| Checklist | [checklist.md](checklist.md) |

---

> **Ảnh hưởng của model thực tế (19/11/2026, [spike](../../spikes/lmstudio.md))** – DeepSeek R1 luôn suy nghĩ (~200–350 token mỗi lời gọi, ~7 token/s):
> - **LLM phân tích câu hỏi (BR-09.6) mặc định TẮT** (`QUERY_ANALYSIS_LLM=false`): một lời gọi mất ≥ 30 s, không thể vừa ngân sách 1.5 s. F09 chạy bằng quy tắc + ý định theo từ khóa (BR-09.9); câu hỏi nối tiếp dùng kế thừa ngữ cảnh bằng quy tắc (§2.1). Chỉ bật khi đổi sang model nhanh hơn.
> - Sinh lại (BR-14.6) tối đa 2 lần → có thể > 4 phút: mặc định dev `ANSWER_MAX_REGENERATIONS=1`.
> - SSE: phát thêm sự kiện `thinking` (chỉ trạng thái "Đang suy nghĩ…", **không** kèm nội dung) trong lúc model đang ở phần `reasoning_content`, để giao diện không như bị treo.
> - Hạn 30 s (BR-08.5) đọc từ `CHAT_GENERATION_TIMEOUT_S`.

## 1. Mục tiêu

Hoàn thiện pipeline hỏi đáp: hiểu câu hỏi tình huống / tổng hợp và câu hỏi nối tiếp bằng LLM (quy tắc vẫn ghi đè thực thể), kiểm tra trích dẫn đầy đủ V1–V6 với sinh lại tối đa 2 lần, và stream câu trả lời qua SSE với các sự kiện F08 §5.

## 2. Thiết kế

### 2.1. Phân tích câu hỏi bằng LLM (F09 §1.2)

```text
qa/analysis/
├── llm.py        # query_analysis: complete_json(LLMQueryOut), timeout 1.5 s (BR-09.6, 09.7)
├── taxonomy_map.py # ánh xạ mờ chu_de / doi_tuong theo tu_khoa, ngưỡng 0.8 (BR-09.8)
├── history.py    # 3 lượt gần nhất: câu hỏi + tóm tắt trả lời (≤ 200 ký tự) + unit_ids đã trích (BR-08.3)
└── analyzer.py   # quy tắc ∥ LLM ∥ kiểm tra ID tồn tại → hợp nhất
```

| Quy tắc | Cách làm |
|---|---|
| Song song (F09 §4) | `asyncio.gather(rules_and_resolve(), llm_analyze(timeout=1.5))`; LLM lỗi / quá hạn → `y_dinh` theo từ khóa (BR-09.9), `llm_used = false` |
| Hợp nhất (BR-09.5) | Số hiệu, điều khoản, ngày: **quy tắc ghi đè LLM**; LLM chỉ bổ sung khi quy tắc không tìm thấy, và bổ sung chỉ được chấp nhận khi chuỗi đó có trong câu hỏi / lịch sử (không bao giờ trả số hiệu ngoài câu hỏi hoặc lịch sử – F09 §7) |
| Câu hỏi nối tiếp | Lịch sử có `unit_ids` → quy tắc "khoản 2" không có Điều / văn bản → kế thừa Điều + văn bản của lượt trước ("còn khoản 2 thì sao?" sau Q1 → `123/2020/NĐ-CP:Đ3:K2`); `cau_hoi_doc_lap` từ LLM dùng cho truy xuất |
| Ngày kế thừa (BR-08.3) | Lượt mới không nêu ngày và UI không chọn → `ngay_ap_dung` lượt trước, `nguon_ngay = lich_su` |
| Định tuyến | Đủ BR-09.10 → 09.14 với `y_dinh` từ LLM; fallback DIRECT/GRAPH rỗng → `LOCAL` (BR-09.15) |

### 2.2. Kiểm tra trích dẫn đầy đủ và sinh lại (F14)

| Mã | Bổ sung so với M09 |
|---|---|
| V5 `HALLUCINATED_REF` | `legal/refs.parse_refs(answer)` → mọi tham chiếu dạng chữ phải thuộc tập `{unit_id ngữ cảnh} ∪ {unit_ids của ý tổng hợp} ∪ {unit_id notice} ∪ {nguon_sua_doi}` (so ở cấp Điều trở xuống: tham chiếu "Điều 19" chấp nhận khi ngữ cảnh có `Đ19:K1`). Tham chiếu tới điều khoản chỉ có trong notice mà câu đó không có từ khóa hết hiệu lực → lỗi (ví dụ F14 §5) |
| V6 `UNKNOWN_DOCUMENT` | Số hiệu đầy đủ trong câu trả lời phải tồn tại trong đồ thị |
| Sinh lại (BR-14.6) | Lỗi → thêm khối `[PHẢN HỒI LẦN TRƯỚC]` liệt kê lỗi cụ thể ("Câu 1 trích [C7] không tồn tại …") → sinh lại, tối đa 2 lần (tổng 3 lần) |
| Hết lượt (BR-14.7) | Bản cuối, xóa câu chứa trích dẫn lỗi, `do_tin_cay = thap`, cảnh báo, danh sách nguồn đã xác minh |
| `attempts` | Lưu vào `query_trace.attempts` và `AnswerResult.attempts` |

### 2.3. SSE stream (F08 §5)

```python
@router.post("/chat/sessions/{id}/messages")
async def post_message(..., body: MessageIn):
    if not body.stream: return await pipeline.answer(...)        # JSON như M09
    return EventSourceResponse(pipeline.answer_stream(...))      # sse-starlette

async def answer_stream(...):
    yield ev("analysis", {...route, ngay_ap_dung, nguon_ngay, van_ban, dieu_khoan})
    r = await retrieve(a, on_progress=lambda i, n: queue.put(ev("progress", {"i": i, "n": n})))
    yield ev("retrieval", {"contexts": len(r.contexts), "notices": len(r.notices)})
    for attempt in range(1, 4):
        async for delta in generator.stream(a, r, feedback):     # gateway.stream_text đã lọc <think>
            yield ev("token", {"text": delta})
        report = verifier.verify(...)
        if report.passed or attempt == 3: break
        yield ev("replace", {"reason": [e.code for e in report.errors]})   # BR-14.10
    yield ev("final", answer_response)                            # AnswerResponse đầy đủ
```

| Vấn đề | Cách làm |
|---|---|
| Thứ tự sự kiện | `analysis` → (`progress`)* → `retrieval` → `token`* → (`replace` → `token`*){0,2} → `final`; `clarify` / từ chối / không tìm thấy → chỉ `analysis` + `final` |
| Hạn 30 s (BR-08.5) | Tổng thời gian sinh vượt 30 s → hủy stream LLM, `replace` + `final` là câu trả lời dự phòng |
| LM Studio tắt giữa chừng | `LLMUnavailable` trong stream → `replace` + `final` dự phòng (đã có ngữ cảnh); trước khi có ngữ cảnh → sự kiện `error` `{code: LLM_UNAVAILABLE}` rồi đóng |
| Client ngắt kết nối | Bắt `asyncio.CancelledError` → hủy lời gọi LLM, vẫn lưu tin nhắn user + trace với `cancelled = true` |
| Keep-alive | Comment SSE mỗi 10 s khi đang chờ map Global |
| Thinking | `CHAT_THINKING` bật → gateway đã lọc; nội dung think chỉ vào `query_trace.raw_output` khi `TRACE_THINKING` |

## 3. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M15-T1 | `llm.py` + prompt `query_analysis` + `taxonomy_map.py` | 2.1 | 09.6–09.9 | 1 ngày |
| M15-T2 | `history.py` + hợp nhất + câu hỏi nối tiếp + ngày kế thừa | 2.1 | 09.5, 08.3 | 0.75 ngày |
| M15-T3 | V5, V6 | 2.2 | F14 §1.2 | 0.75 ngày |
| M15-T4 | Sinh lại + BR-14.7 đầy đủ | 2.2 | 14.6, 14.7 | 0.5 ngày |
| M15-T5 | `generator.stream` + `answer_stream` + SSE | 2.3 | 08.4, 08.5, 14.10, 14.11 | 1 ngày |
| M15-T6 | Ngoại lệ stream (30 s, LM Studio tắt, client ngắt) | 2.3 | 08.5 | 0.5 ngày |
| M15-T7 | Golden Q1–Q5 + câu nối tiếp + đo P95 | – | – | 0.5 ngày |

## 4. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit | Hợp nhất: LLM trả số hiệu không có trong câu → bị bỏ; quy tắc có điều khoản → ghi đè LLM |
| Unit | Ánh xạ mờ `"ho kinh doanh"` → `ho_kinh_doanh`; mã lạ → bỏ |
| Tích hợp | Sau Q1, "còn khoản 2 thì sao?" → `123/2020/NĐ-CP:Đ3:K2`, route `DIRECT` |
| Tích hợp | LLM phân tích quá 1.5 s (mock) → vẫn trả `QueryAnalysis` với `llm_used = false` |
| Unit V5 | Ví dụ F14 §5: trích "khoản 10 Điều 3 NĐ 123" như quy định hiện hành khi chỉ có ở N1 → `HALLUCINATED_REF` |
| Tích hợp (mock) | Lần 1 sai nhãn, lần 2 đúng → có 1 sự kiện `replace`, `attempts = 2`, `do_tin_cay = cao` |
| Tích hợp (mock) | Sai cả 3 lần → `do_tin_cay = thap`, câu lỗi bị xóa |
| SSE | Kiểm tra thứ tự sự kiện cho DIRECT, GLOBAL (có `progress`), CLARIFY |
| SSE | Delta chứa `<think>` cắt ngang → không lộ ra `token` |
| SSE | Tắt mock LM Studio giữa stream → `replace` + `final` dự phòng, không treo |
| Hiệu năng | P95 ≤ 10 s trên câu hỏi route ≠ GLOBAL (máy dev, ghi cấu hình) |

## 5. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| `query_analysis` 1.5 s quá ngắn với Qwen 9B local | Đã có fallback quy tắc; đo tỷ lệ `llm_used`; tăng hạn nếu chấp nhận được trong ngân sách 10 s |
| Sinh lại làm P95 vượt 10 s | Đo `attempts`; cải thiện prompt nếu tỷ lệ sinh lại > 20% |
| Người dùng thấy bản nháp sai trước khi bị thay | Nhãn "Đang kiểm tra nguồn…" trên bản nháp (BR-14.10); M10 làm mờ bản nháp |

## 6. Bàn giao

- M10 đợt 2 tiêu thụ đúng thứ tự sự kiện ở 2.3.
- M17 dùng `pipeline.answer(stream=false)`; `attempts` và `do_tin_cay` là trường đầu vào phân tích lỗi.
