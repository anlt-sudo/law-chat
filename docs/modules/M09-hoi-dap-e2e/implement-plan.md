# M09 – Hỏi đáp end-to-end (không stream) · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F09 – Phân tích câu hỏi](../../features/F09-phan-tich-cau-hoi.md) (quy tắc), [F14 – Sinh & kiểm tra trích dẫn](../../features/F14-sinh-tra-loi-kiem-tra-trich-dan.md) (cơ bản), [F08 – Chat](../../features/F08-hoi-dap-chat.md) (không stream) |
| Giai đoạn | PoC – tuần 4 |
| Ước lượng | 4–5 ngày |
| Phụ thuộc | M07, M08, M01 |
| Module dùng kết quả | M10, M15 (mở rộng), M17 |
| Checklist | [checklist.md](checklist.md) |

---

> **Ảnh hưởng của model thực tế (19/11/2026, [spike](../../spikes/lmstudio.md))** – DeepSeek R1 0528 Qwen3 8B luôn suy nghĩ, ~7 token/s:
> - Phân tích câu hỏi **chỉ bằng quy tắc** (đúng phạm vi M09) – không có gì thay đổi.
> - Sinh câu trả lời mất ~60–90 s → timeout cứng BR-08.5 (30 s) đặt qua `CHAT_GENERATION_TIMEOUT_S` (mặc định dev 180 s); golden test với LM Studio thật dùng timeout tương ứng.
> - `max_tokens` của `chat_answer` = 1 024 + `LLM_REASONING_BUDGET` (M01 §2b), nếu không model hết token khi đang suy nghĩ.
> - Đo và ghi `latency_ms` thực tế; KPI P95 ≤ 10 s **không đạt được** với cấu hình này – ghi vào báo cáo, không chặn PoC.

## 1. Mục tiêu

Một đường xuyên suốt: `POST /chat/sessions/{id}/messages` (`stream=false`) → phân tích bằng quy tắc → DIRECT / GRAPH (LOCAL tạm bằng BM25) → **lọc hiệu lực** → Qwen sinh câu trả lời có `[Cx]` → kiểm tra trích dẫn → lưu lượt hỏi đáp. Demo được Q1, Q5 và ví dụ inception §5.3.

## 2. Phạm vi

| Trong M09 | Để M15 |
|---|---|
| F09 BR-09.1 → BR-09.5 (quy tắc), ý định theo từ khóa (BR-09.9), định tuyến BR-09.10 → 09.15 | LLM phân tích (BR-09.6 → 09.8), viết lại câu hỏi nối tiếp |
| Route `DIRECT`, `GRAPH`, `REFUSE`, `CLARIFY`; `LOCAL` / `GLOBAL` tạm → BM25 + lọc hiệu lực | `LOCAL` thật (M13), `GLOBAL` thật (M14) |
| F14 dựng prompt, sinh (không stream), kiểm tra V1, V2, V4, V3 (từ khóa) | V5, V6, sinh lại tối đa 2 lần, sự kiện `replace` |
| F08 phiên chat, giới hạn, ngày áp dụng, dự phòng khi LLM lỗi, lưu trace | SSE stream, hội thoại nhiều lượt đầy đủ |
| Golden test Q1, Q5, inception §5.3 | Bộ đánh giá ≥ 50 câu (M17) |

Khi kiểm tra trích dẫn không đạt ở PoC: không sinh lại, trả `do_tin_cay = thap` + cảnh báo, xóa câu chứa trích dẫn lỗi (BR-14.7 rút gọn).

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/qa/
├── analysis/
│   ├── models.py        # Route, YDinh, QueryAnalysis, LLMQueryOut (F09 §6)
│   ├── rules.py         # regex số hiệu, điều khoản, ngày (BR-09.1 → 09.4)
│   ├── resolve_doc.py   # alias → VanBan qua fulltext index vanban_alias (BR-09.2)
│   ├── intent.py        # ý định theo từ khóa (bảng F09 §1.3)
│   ├── routing.py       # BR-09.10 → 09.15
│   ├── analyzer.py      # analyze(question, history, ngay_ui) → QueryAnalysis
│   └── router.py        # POST /query/analyze, GET /documents/resolve
├── answer/
│   ├── prompt.py        # gán nhãn C/N, dựng prompt (BR-14.1 → 14.4, khung F14 §6.2)
│   ├── generator.py     # generate(...) → AnswerResult
│   ├── verifier.py      # V1–V4 (PoC), V5–V6 (M15)
│   ├── citations.py     # nhãn → Citation (BR-14.8)
│   ├── fallback.py      # câu trả lời dự phòng (BR-08.5), câu cố định "không tìm thấy"
│   └── router.py        # POST /answer/generate, /answer/verify
├── chat/
│   ├── models.py        # ORM chat_session, chat_message, message_citation, query_trace
│   ├── limits.py        # ≤ 1000 ký tự, 20 câu/phút/key, 1 câu đang xử lý/phiên
│   ├── pipeline.py      # điều phối F09 → F10/BM25 → F13 → F14
│   ├── service.py       # phiên, lưu lượt
│   └── router.py        # /chat/sessions...
└── constants.py         # DISCLAIMER, thông điệp cố định
backend/tests/e2e/
├── golden.yaml          # Q1, Q5, inception 5.3 (+ biến thể ngày)
└── test_golden.py       # chạy với mock LLM (CI) hoặc LM Studio thật (@lmstudio)
```

### 3.2. Phân tích câu hỏi (quy tắc)

| Bước | Cách làm |
|---|---|
| Số hiệu đầy đủ (BR-09.1) | `\d+/\d{4}/[A-ZĐ0-9\-]+` → khớp `VanBan.so_hieu` (chuẩn hóa NFC, hoa thường) |
| Số hiệu rút gọn (BR-09.2) | Regex `(Nghị định|NĐ|Thông tư|TT|Nghị quyết|NQ|Luật|Quyết định|QĐ)\s*(số\s*)?(\d+)(/\d{4})?` → truy vấn fulltext `vanban_alias` + lọc loại; > 1 văn bản cùng loại cùng số → ưu tiên văn bản trong phạm vi dữ liệu; vẫn > 1 → `CLARIFY` + `lua_chon_lam_ro` |
| Điều khoản (BR-09.3) | Dùng lại `legal/refs.parse_refs` với `current_so_hieu` = văn bản gần nhất trong câu; không có văn bản → lấy từ lượt trước (lịch sử) → không có → `CLARIFY` |
| Ngày (BR-09.4) | `dd/mm/yyyy`, `dd-mm-yyyy`, `ngày d tháng m năm y` → ngày cụ thể; `tháng m/yyyy` → ngày 01, `ngay_mo_ho`; `năm yyyy` → 01/01, `ngay_mo_ho`; "hiện nay", "hiện hành", không nêu → hôm nay |
| Ngày áp dụng (BR-08.2) | UI > câu hỏi > lượt trước (BR-08.3: kế thừa) > hôm nay; ghi `nguon_ngay` |
| Ý định (BR-09.9) | Bảng từ khóa F09 §1.3, xét theo thứ tự `ngoai_pham_vi` → `liet_ke_sua_doi` → `tong_hop` → `hieu_luc` → `lich_su` → `noi_dung` (cần điều khoản) → `tinh_huong` |
| Ngoài phạm vi | Mẫu xin tư vấn cá nhân ("tôi có nên", "có bị phạt không nếu tôi…", "giúp tôi viết…") |
| Không bịa số hiệu | `van_ban` chỉ chứa số hiệu có trong câu hỏi / lịch sử và tồn tại trong đồ thị; tồn tại trong câu nhưng không có trong đồ thị → `van_ban_khong_co` |

### 3.3. Pipeline chat (PoC)

```python
async def answer(session, content, ngay_ui) -> AnswerResponse:
    mark_interactive()                                   # M01 – nhường batch
    t = Timer()
    a = await analyzer.analyze(content, history=last_turns(session, 3), ngay_ui=ngay_ui)
    if a.route == REFUSE:  return refuse_answer(a)        # BR-08.6
    if a.route == CLARIFY: return clarify_answer(a)
    r = await retrieve(a)                                # DIRECT | GRAPH | BM25 tạm
    if a.route in (DIRECT, GRAPH) and not r.contexts and not r.notices:
        a.fallback_from, a.route = a.route, LOCAL; r = await retrieve(a)   # BR-09.15
    r = effectivity.filter(r, a.ngay_ap_dung)            # BR-08.1 – không bao giờ bỏ qua
    if not r.contexts and not r.notices: return not_found_answer(a)
    try:
        res = await asyncio.wait_for(generator.generate(a, r), timeout=30)  # BR-08.5
    except (asyncio.TimeoutError, LLMUnavailable, LLMTimeout):
        res = fallback.from_contexts(r)                  # danh sách điều khoản + trích đoạn
    save_turn(session, a, r, res, t.latency())
```

"BM25 tạm" cho `LOCAL` / `GLOBAL` ở PoC: `bm25_search(cau_hoi_goc, ngay, so_hieu=a.van_ban, tu_khoa=…, k=12)` → `ContextItem(chinh, nguon_truy_xuat="bm25")`. Ghi `debug.temporary_local = true` trong trace.

### 3.4. Sinh câu trả lời

- Nhãn `[C1]…[Cn]` theo thứ tự điểm, `[N1]…[Nm]` cho notice; mỗi khối: nhãn điều khoản, số hiệu, khoảng hiệu lực, vai trò, nguồn sửa đổi, nội dung (BR-14.1, 14.2).
- System prompt theo khung F14 §6.2, đủ 7 quy tắc BR-14.3; `structured_result` → bảng rút gọn (BR-14.4).
- Gọi `gateway.complete_text("chat_answer", messages)` (thinking theo `CHAT_THINKING`, đã lọc `<think>`), `max_tokens = 1024`.
- Ước lượng token trước khi gọi; `ContextTooLong` → bỏ bớt ngữ cảnh điểm thấp nhất rồi thử lại.

### 3.5. Kiểm tra trích dẫn (PoC)

| Mã | Cách kiểm |
|---|---|
| V1 `UNKNOWN_REF` | Regex `\[(C|N)\d+\]` → mọi nhãn phải có trong danh sách |
| V2 `EXPIRED_CITATION` | `effectivity.check(unit_ids của các [Cx] được trích, ngay)` → phải `con_hieu_luc` và đúng `phien_ban_id` |
| V3 `NOTICE_AS_CURRENT` | Câu chứa `[Nx]` phải chứa ≥ 1 từ khóa: bãi bỏ, hết hiệu lực, được thay thế, trước đây, đã sửa đổi, không còn |
| V4 `NO_CITATION` | Câu trả lời không phải câu "không tìm thấy" phải có ≥ 1 `[Cx]` |

Tách câu theo `. ! ?` + xuống dòng (giữ dấu chấm trong số hiệu `123/2020/NĐ-CP` và "Điều 3." – dùng regex tách câu bỏ qua số).

Không đạt → xóa câu chứa lỗi, `do_tin_cay = thap`, cảnh báo "Câu trả lời có thể chưa đầy đủ, vui lòng kiểm tra nguồn". Nhãn còn lại → `Citation` (00-common §7, BR-14.8); luôn gắn disclaimer (BR-14.9).

### 3.6. Chat API & lưu trữ

- Migration `0008_chat`: `chat_session`, `chat_message`, `message_citation`, `query_trace` đúng F08 §6.
- API F08 §5 (trừ SSE): sessions CRUD (xóa mềm), `POST /messages` (`stream=false` bắt buộc ở PoC; `stream=true` → 400 `STREAM_NOT_SUPPORTED_YET`), `GET /chat/messages/{id}/trace` (biên tập viên).
- Giới hạn (BR-08.10): độ dài → 422; 20 câu/phút/key → 429 (đếm bằng `chat_message` trong 60 s hoặc bộ đếm trong bộ nhớ); phiên đang có câu xử lý → 409 `SESSION_BUSY` (khóa advisory PG theo `session_id`).
- `latency_ms` từng bước: `analysis`, `retrieval`, `generation`, `verification`, `total`.
- `query_trace` lưu ngữ cảnh trước / sau lọc, notices, prompt, kết quả kiểm tra; `raw_output` chỉ khi `TRACE_THINKING`. **Không** lưu `<think>` vào `chat_message.content` (F14 §7).

### 3.7. Golden test

`golden.yaml`:

```yaml
- id: Q1
  question: "Khoản 10 Điều 3 Nghị định 123/2020 hiện còn hiệu lực không?"
  ngay: today
  expect:
    route: DIRECT
    citations_include_notice: ["123/2020/NĐ-CP:Đ3:K10"]
    answer_contains_any: ["bãi bỏ", "hết hiệu lực"]
    mentions: ["70/2025/NĐ-CP"]
- id: Q1-past
  question: "Khoản 10 Điều 3 Nghị định 123/2020 còn hiệu lực không?"
  ngay: 2025-03-15
  expect: {route: DIRECT, citations_active: ["123/2020/NĐ-CP:Đ3:K10"]}
- id: Q5
  question: "NĐ 70/2025 đã sửa những điều nào của NĐ 123?"
  expect: {route: GRAPH, structured_result_matches_graph: true}
- id: I53
  question: "Thủ tục hủy hóa đơn lập sai theo khoản 10 Điều 3 Nghị định 123 là gì?"
  expect: {route: DIRECT, answer_contains_any: ["bãi bỏ"], citations_active_include: ["123/2020/NĐ-CP:Đ19"]}
```

Chạy 2 chế độ: mock LLM (trả câu trả lời dựng sẵn có nhãn đúng / sai để test verifier) trong CI; LM Studio thật (`@lmstudio`) để demo. Script `scripts/golden.py` in bảng kết quả – tiền thân của M17.

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M09-T1 | Models + `rules.py` + `resolve_doc.py` | 3.2 | 09.1–09.4 | 1 ngày |
| M09-T2 | `intent.py` + `routing.py` + `analyzer.py` + API | 3.2 | 09.5, 09.9–09.15 | 0.5 ngày |
| M09-T3 | `prompt.py` + `generator.py` | 3.4 | 14.1–14.5 | 0.5 ngày |
| M09-T4 | `verifier.py` (V1–V4) + `citations.py` + `fallback.py` | 3.5 | 14.7–14.9, 08.5 | 0.75 ngày |
| M09-T5 | Migration chat + `limits.py` + `service.py` | 3.6 | 08.9, 08.10 | 0.5 ngày |
| M09-T6 | `pipeline.py` + chat API | 3.3, 3.6 | 08.1–08.7 | 0.5 ngày |
| M09-T7 | Golden test + script | 3.7 | – | 0.5 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit `rules` | Bảng ca: số hiệu đầy đủ / rút gọn / sai; "điểm a khoản 4 Điều 9"; 6 dạng ngày; ngày mơ hồ |
| Unit `routing` | Q1 → DIRECT, Q5 → GRAPH, câu "tôi có nên…" → REFUSE, "NĐ 123" khớp 2 văn bản → CLARIFY |
| Unit `verifier` | Câu trả lời giả có `[C7]` không tồn tại → `UNKNOWN_REF`; `[N1]` trong câu khẳng định hiện hành → `NOTICE_AS_CURRENT`; không có `[Cx]` → `NO_CITATION` |
| Tích hợp | LM Studio tắt → câu trả lời dự phòng có danh sách điều khoản; không treo |
| Tích hợp | 21 câu trong 1 phút → câu thứ 21 trả 429; gửi câu thứ hai khi câu đầu chưa xong → 409 |
| E2E | Golden Q1, Q1-past, Q5, I53 |
| Kiểm tra | `SELECT count(*) FROM chat_message WHERE content LIKE '%<think>%'` = 0 |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Qwen 9B không gắn nhãn `[Cx]` ổn định | Few-shot 1 ví dụ trong system prompt; verifier bắt lỗi; M15 thêm sinh lại |
| Độ trễ > 10 s trên máy dev (thinking bật) | Đo `latency_ms`; thử `CHAT_THINKING=false` cho PoC nếu cần |
| BM25 tạm cho LOCAL trả lời kém | Chỉ là tạm; PoC demo tập trung Q1, Q5 |
| Tách câu sai do dấu chấm trong số hiệu | Test riêng cho tách câu |

## 7. Bàn giao

- M15 thay `intent.py` bằng LLM + quy tắc, bật sinh lại trong `generator`, thêm SSE vào `chat/router.py` – pipeline giữ nguyên thứ tự.
- M13, M14 thay nhánh "BM25 tạm" trong `pipeline.retrieve`.
- M17 dùng `pipeline.answer` với `stream=false` làm runner đánh giá.
