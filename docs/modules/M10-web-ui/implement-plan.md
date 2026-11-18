# M10 – Web chat & màn hình văn bản · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | Giao diện của [F08](../../features/F08-hoi-dap-chat.md), [F10 UC-10.3](../../features/F10-tra-cuu-truc-tiep.md), [F05](../../features/F05-duyet-quan-he.md), [F16](../../features/F16-danh-gia-phan-hoi.md), trang quản trị F07 / F15 / F17 |
| Giai đoạn | Đợt 1: PoC – tuần 4 · Đợt 2: MVP – tuần 10 |
| Ước lượng | Đợt 1: 2–3 ngày · Đợt 2: 2–3 ngày |
| Phụ thuộc | Đợt 1: M09, khung frontend M05 · Đợt 2: M14, M15, M16, M17 |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

- **Đợt 1 (PoC):** người dùng hỏi trên web, thấy câu trả lời có trích dẫn kèm trạng thái hiệu lực, bấm trích dẫn để mở trang văn bản với cây cấu trúc và dòng thời gian phiên bản. Đủ để demo Q1, Q5.
- **Đợt 2 (MVP):** chat stream, phản hồi 👍/👎, trang chủ đề, trang quản trị (LLM, pipeline, độ trễ cập nhật, KPI đánh giá), hoàn thiện trang duyệt.

## 2. Công nghệ (đề xuất)

| Nhóm | Lựa chọn | Ghi chú |
|---|---|---|
| Khung | React 18 + Vite + TypeScript | Đã tạo ở M05 |
| Routing | React Router | |
| Dữ liệu | TanStack Query | Cache, refetch, trạng thái loading |
| UI | Tailwind CSS + một bộ component headless (ví dụ Radix) | Đề xuất; nhóm có thể đổi |
| Markdown | `react-markdown` | Câu trả lời là Markdown có nhãn `[Cx]` |
| SSE qua POST (đợt 2) | `@microsoft/fetch-event-source` | `EventSource` gốc không hỗ trợ POST và header `X-API-Key` |
| Kiểu dữ liệu | Sinh type từ OpenAPI của FastAPI (`openapi-typescript`) | Tránh lệch schema |

## 3. Màn hình

### 3.1. Đợt 1 – PoC

| Route | Nội dung | API |
|---|---|---|
| `/` → `/chat` | Sidebar phiên (tạo, đổi tên, xóa); khung hội thoại; ô nhập (đếm ký tự ≤ 1000); **bộ chọn ngày áp dụng** (mặc định hôm nay) | `/chat/sessions*`, `POST /messages` (`stream=false`) |
| Tin nhắn trợ lý | Markdown; nhãn `[C1]` thành chú thích bấm được; dòng "Ngày áp dụng: …" + cảnh báo `ngay_mo_ho`; khối **Nguồn** (label, khoảng hiệu lực, huy hiệu trạng thái: xanh còn hiệu lực / đỏ hết hiệu lực / xám chưa có hiệu lực), khối **Lưu ý** (notice); bảng `structured_result` (Q5); `do_tin_cay = thap` → banner vàng; disclaimer | – |
| Clarify | Nút lựa chọn văn bản; bấm → gửi lại câu hỏi kèm số hiệu đã chọn | – |
| `/van-ban/:slug?ngay=` | Metadata + trạng thái tại ngày; cây Chương / Điều / Khoản tô màu theo trạng thái; tab quan hệ đi / đến; chọn một Khoản → panel dòng thời gian phiên bản (thanh ngang theo năm) + nội dung từng phiên bản + sự kiện | `/documents/{slug}`, `/structure`, `/relations`, `/units/versions` |
| Mở từ trích dẫn | `/van-ban/:slug?ngay=<ngày áp dụng>&unit=<unit_id>` → cuộn tới và mở dòng thời gian | – |
| Cài đặt | Nhập API key (localStorage), hiển thị vai trò | – |

### 3.2. Đợt 2 – MVP

| Route / thành phần | Nội dung | API |
|---|---|---|
| Chat stream | Gửi `stream=true`; sự kiện `analysis` (hiện route + ngày), `retrieval` (số ngữ cảnh), `progress` (Global: "Đang tổng hợp cụm 2/3"), `token` (nối chữ, nhãn "Đang kiểm tra nguồn…"), `replace` (xóa bản nháp, "Đang soạn lại câu trả lời…"), `clarify`, `final` (thay toàn bộ bằng kết quả chính thức), lỗi 503 | SSE `POST /messages` |
| Hủy câu hỏi | Nút dừng → hủy request (AbortController) | – |
| Phản hồi | 👍 / 👎 trên mỗi câu trả lời; 👎 mở form lý do (6 lựa chọn F16 BR-16.7) + bình luận; sửa được | `POST /chat/messages/{id}/feedback` |
| `/chu-de` | Danh sách cụm / chủ đề (tiêu đề, tóm tắt, văn bản chính); trang chủ đề lọc theo đối tượng + ngày | `/topics`, `/topics/{ma_chu_de}/documents` |
| `/tim-kiem` | Ô tìm kiếm điều khoản (Local Search) có bộ lọc chủ đề / đối tượng / ngày | `POST /search/local` |
| `/bien-tap/duyet` | Hoàn thiện trang duyệt M05: thống kê theo tuần, lọc theo rule | `/review/*` |
| `/bien-tap/phan-hoi` | Hàng đợi phản hồi (ưu tiên `quy_dinh_het_hieu_luc`), xem trace, 3 hành động; "Tạo câu hỏi chuẩn" điền sẵn form | `/feedback/*`, `/chat/messages/{id}/trace` |
| `/bien-tap/danh-gia` | Bộ câu hỏi chuẩn (CRUD); lượt đánh giá; kết quả từng câu; ghi đè chấm điểm | `/eval/*` |
| `/quan-tri` | Thẻ LLM (health, model, mạch, hàng đợi, P50/P95 theo tác vụ); pipeline (lịch, lượt chạy, job lỗi + nút chạy lại); độ trễ cập nhật + văn bản trễ hạn; chỉ mục (stale, cụm dirty); KPI lượt đánh giá gần nhất so với lượt trước | `/admin/llm/*`, `/admin/pipeline/*`, `/admin/schedules`, `/admin/freshness`, `/index/status`, `/eval/runs` |

Menu hiển thị theo vai trò: `nguoi_dung` (chat, văn bản, chủ đề, tìm kiếm), `bien_tap_vien` (+ biên tập), `quan_tri` (+ quản trị).

## 4. Cấu trúc thư mục

```text
frontend/src/
├── api/ (client.ts, types.gen.ts, chat.ts, documents.ts, review.ts, eval.ts, admin.ts, sse.ts)
├── components/
│   ├── AnswerMessage.tsx      # markdown + chú thích [Cx]
│   ├── CitationList.tsx, NoticeList.tsx, EffectivityBadge.tsx
│   ├── StructuredResultTable.tsx
│   ├── VersionTimeline.tsx
│   ├── DocumentTree.tsx
│   └── FeedbackButtons.tsx    # đợt 2
├── pages/ (Chat.tsx, Document.tsx, Topics.tsx, Search.tsx, review/*, feedback/*, eval/*, admin/*)
└── lib/ (dates.ts – định dạng dd/mm/yyyy, role.ts)
```

## 5. Các bước triển khai

| Mã | Công việc | Đợt | Ước lượng |
|---|---|---|---|
| M10-T1 | Layout chung, routing, menu theo vai trò, sinh type từ OpenAPI | 1 | 0.5 ngày |
| M10-T2 | Trang chat (phiên, gửi câu hỏi non-stream, ngày áp dụng, clarify) | 1 | 0.75 ngày |
| M10-T3 | `AnswerMessage`, `CitationList`, `NoticeList`, `EffectivityBadge`, `StructuredResultTable` | 1 | 0.75 ngày |
| M10-T4 | Trang văn bản: cây, quan hệ, `VersionTimeline`, mở từ trích dẫn | 1 | 0.75 ngày |
| M10-T5 | Chat stream SSE + hủy + xử lý mọi sự kiện | 2 | 0.75 ngày |
| M10-T6 | Phản hồi 👍/👎 + trang phân loại phản hồi | 2 | 0.5 ngày |
| M10-T7 | Trang chủ đề + tìm kiếm | 2 | 0.5 ngày |
| M10-T8 | Trang đánh giá (câu hỏi chuẩn, lượt, kết quả, ghi đè) | 2 | 0.5 ngày |
| M10-T9 | Trang quản trị | 2 | 0.5 ngày |

## 6. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Component (Vitest + Testing Library) | `AnswerMessage` chuyển `[C1]` thành chú thích; nhãn không có trong `citations` hiển thị thường, không vỡ |
| Component | `EffectivityBadge` đủ 4 trạng thái; `VersionTimeline` với phiên bản mở (`hieu_luc_den = null`) |
| Component | Bộ xử lý SSE: chuỗi `token` → `replace` → `token` → `final` cho nội dung cuối đúng `final` |
| E2E thủ công (kịch bản demo) | Q1 → thấy "đã bị bãi bỏ" + huy hiệu đỏ ở C1 → bấm → trang NĐ 123 mở khoản 10 Điều 3, dòng thời gian kết thúc 01/6/2025; đổi ngày áp dụng 15/3/2025 → câu trả lời khác |
| E2E thủ công | Q5 → bảng `structured_result` đủ dòng |
| Tương thích | Chrome, Edge mới nhất; màn hình ≥ 1280 px (bản dev) |

## 7. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Người dùng hiểu câu trả lời là tư vấn pháp lý (rủi ro inception §8) | Disclaimer luôn hiển thị, không ẩn được; ngày áp dụng và trạng thái hiệu lực luôn hiện |
| API key lưu localStorage | Chấp nhận ở bản dev; ghi rõ trong README, không dùng key quản trị trên máy chung |
| Lệch schema giữa backend và frontend | Sinh type từ OpenAPI trong CI; build frontend lỗi khi schema đổi |
