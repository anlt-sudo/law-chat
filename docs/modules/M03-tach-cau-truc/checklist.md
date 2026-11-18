# M03 – Tách cấu trúc & ghi đồ thị · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F03](../../features/F03-tach-cau-truc.md)

## Chuẩn bị

- [ ] Fixture M02 đã `NORMALIZED`; `manifest.yaml` có số Chương / Điều kỳ vọng cho ít nhất NĐ 123 và NĐ 70
- [ ] Duyệt bổ sung label `:DonVi` + constraint `donvi_id`

## Triển khai

- [ ] M03-T1 `legal/doc_types.py`: `NĐ-CP` → Nghị định / Chính phủ; `TT-BTC` → Thông tư / Bộ Tài chính; `QH15` → Luật hoặc Nghị quyết theo tiêu đề; `QĐ-TTg` → Quyết định / Thủ tướng
- [ ] M03-T1 `legal/labels.py` nhãn cho Văn bản / Chương / Điều / Khoản / Điểm / Phiên bản
- [ ] M03-T1 `legal/aliases.py` sinh `NĐ 123/2020`, `Nghị định 123/2020`, `Nghị định số 123/2020/NĐ-CP`, `NĐ 123`…
- [ ] M03-T2 Metadata: số hiệu (cả `QH\d+`), ngày ban hành, trích yếu; đối chiếu `metadata_nguon`, giá trị từ nội dung được ưu tiên
- [ ] M03-T3 Máy trạng thái: Chương, Mục (không tạo node), Điều (hậu tố `a`), Khoản, Điểm (`đ`)
- [ ] M03-T3 Dòng đánh số ở "Căn cứ" và phụ lục không tạo Khoản / Điểm
- [ ] M03-T3 Khối “…” sau "như sau:" không sinh node, lưu `noi_dung_trich`; cảnh báo `UNBALANCED_QUOTE`
- [ ] M03-T3 Điều không chia khoản → PhienBan gắn ở Điều
- [ ] M03-T4 Cảnh báo nhảy số Điều / Khoản / Điểm
- [ ] M03-T5 `legal/refs.py`: đơn, liệt kê, khoảng "từ … đến …", "Nghị định này", kế thừa đích mặc định
- [ ] M03-T6 Ngày hiệu lực: 4 mẫu BR-03.5 + hiệu lực riêng từng phần (BR-03.6)
- [ ] M03-T6 Không có ngày hiệu lực → `hieu_luc_tu = NULL`, `NEEDS_ATTENTION`
- [ ] M03-T7 PhienBan GOC: nội dung Khoản gồm câu dẫn + mọi Điểm; `diem[]`; `content_hash`; `embedding_stale = true`
- [ ] M03-T8 Ghi Neo4j 1 transaction, `MERGE` theo ID, cạnh `CO {thu_tu}`, `BAN_HANH_BOI`, label `:DonVi`
- [ ] M03-T8 Tách lại: xóa node thừa không bị tham chiếu; bị tham chiếu → `ORPHAN_REFERENCED`
- [ ] M03-T9 Migration `0004_parsing`; runner `parse`: `NO_SO_HIEU` / `NO_STRUCTURE` → `FAILED`; thành công → `PARSED` + `enqueue("extract")`
- [ ] M03-T10 `POST /ingest/source-documents/{id}/parse`
- [ ] M03-T10 `GET /documents`, `GET /documents/{slug}/structure`, `GET /documents/{slug}/parse-report`
- [ ] M03-T10 `PATCH /documents/{slug}/metadata`: kiểm tra hồi tố, ghi `metadata_audit`, `NEEDS_ATTENTION → PARSED`, enqueue hợp nhất lại khi cần

## Kiểm thử

- [ ] Unit structure ("Căn cứ" đánh số, Điều không khoản, điểm `đ`, Điều `9a`)
- [ ] Unit quoted (khối NĐ 70 chứa `Điều 9.` không sinh node)
- [ ] Unit effective_date (4 mẫu + hiệu lực riêng)
- [ ] Unit refs (bảng ca kiểm thử)
- [ ] Unit labels
- [ ] Golden snapshot `stats` mọi fixture
- [ ] Tích hợp tách 2 lần số node không đổi
- [ ] Tích hợp PATCH metadata (422 hồi tố, audit)

## Tiêu chí chấp nhận (F03 §7)

- [ ] NĐ 123/2020 tách ra node `123/2020/NĐ-CP:Đ3:K10` với nội dung đúng
- [ ] NĐ 70/2025: nội dung trong “…” không sinh Khoản / Điểm của NĐ 70; được lưu trong `quoted_blocks`
- [ ] Tách lại cùng văn bản → số node Neo4j không đổi
- [ ] `hieu_luc_tu` NĐ 70/2025 = `2025-06-01`; NQ 198/2025 phần thuế khoán = `2026-01-01`

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Mọi fixture `PARSED` hoặc `NEEDS_ATTENTION` có lý do; parse report không còn cảnh báo chưa giải thích ở 5 văn bản inception
