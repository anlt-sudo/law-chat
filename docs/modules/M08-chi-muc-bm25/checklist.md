# M08 – Chỉ mục BM25 · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F07](../../features/F07-lap-chi-muc.md) (phần BM25)

## Chuẩn bị

- [ ] ES có plugin `analysis-icu` (spike M00-T12 đạt)
- [ ] M06 ghi `index_outbox` cho bộ PoC

## Triển khai

- [ ] M08-T1 Index `phien_ban_v1` + alias `phien_ban`, analyzer `vi_standard`, `vi_folded`, mapping F07 §6.1
- [ ] M08-T1 `ensure_index()` khi khởi động
- [ ] M08-T2 Document: `_id = phien_ban_id`, `unit_id`, `so_hieu`, `loai_van_ban`, `label`, `noi_dung` có tiền tố tiêu đề Điều, `hieu_luc_tu`, `hieu_luc_den` (NULL → `9999-12-31`), `chu_de`, `doi_tuong`
- [ ] M08-T3 Sync incremental từ `index_outbox` (lô 500, `SKIP LOCKED`, đánh dấu `processed_at` từng item thành công)
- [ ] M08-T3 Sync full: upsert mọi PhienBan, xóa doc thừa
- [ ] M08-T3 Retry ES 3 lần → `FAILED`
- [ ] M08-T4 Văn bản `CONSOLIDATED` đủ doc → `INDEXED` + `indexed_at`
- [ ] M08-T5 `bm25_search`: multi_match `noi_dung`, `noi_dung.folded`, `label^0.5`; `tu_khoa` boost 2; chủ đề / đối tượng là boost; range hiệu lực; lọc `so_hieu`
- [ ] M08-T6 Migration `index_run`, cột `source_document.indexed_at`
- [ ] M08-T6 `POST /index/runs`, `GET /index/runs/{id}`, `GET /index/status`

## Kiểm thử

- [ ] `_analyze`: có dấu / không dấu cùng token
- [ ] Số doc ES = số `PhienBan`, `outbox_pending = 0`
- [ ] "huy hoa don": có K10 tại 2025-03-15, không có tại 2026-11-18
- [ ] Thu hồi cạnh → doc ES bị xóa
- [ ] `full` 2 lần không đổi số doc
- [ ] ES tắt → `FAILED`, outbox còn nguyên

## Tiêu chí chấp nhận (F07 §7, phần BM25)

- [ ] Sau F06 trên bộ PoC, số document ES = số `PhienBan`
- [ ] Tìm "huy hoa don" (không dấu) qua ES trả về khoản 10 Điều 3 NĐ 123 (với ngày áp dụng trước 01/6/2025)

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] M07-T7 đã nối `RelatedSearch` vào `bm25_search`
- [ ] Toàn bộ văn bản PoC ở trạng thái `INDEXED`
