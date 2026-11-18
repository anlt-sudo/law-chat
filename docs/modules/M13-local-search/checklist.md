# M13 – Local Search · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F11](../../features/F11-local-search.md)

## Chuẩn bị

- [ ] M12 xong: `phien_ban_stale = 0`, vector index hoạt động
- [ ] Câu hỏi Q2, Q4 + 5–10 câu tình huống khác có kỳ vọng điều khoản (nháp cho M17)

## Triển khai

- [ ] M13-T1 Vector top 90 → lọc hiệu lực phiên bản + văn bản → top 30, lọc `so_hieu`
- [ ] M13-T1 Vector top 10 không lọc → notice cho phần tử hết hiệu lực (≤ 3)
- [ ] M13-T2 RRF `Σ 1/(60 + rank)` theo `unit_id`; boost +0.1 chủ đề / đối tượng (không lọc cứng)
- [ ] M13-T2 Top 10 hạt giống
- [ ] M13-T3 Mở rộng 1 bước: tiêu đề Điều cha, Khoản anh em (hạt giống < 200 ký tự), `VIEN_DAN` ra, `HUONG_DAN` vào, `SUA_DOI` vào → `nguon_sua_doi`; ≤ 20 node; 1 truy vấn `UNWIND`
- [ ] M13-T3 Điểm mở rộng = 0.5 × hạt giống; khử trùng theo `unit_id`
- [ ] M13-T3 Node mở rộng qua `EffectivityService.filter`
- [ ] M13-T4 Ngân sách ~3 000 token, cắt tại ranh giới điểm; rỗng → trả notices
- [ ] M13-T5 Embedding lỗi → chỉ BM25, `degraded = true`; ES lỗi → chỉ vector
- [ ] M13-T5 Cấu hình `LOCAL_*` (F11 §6.3)
- [ ] M13-T5 `POST /search/local` có `debug`
- [ ] M13-T6 Route `LOCAL` trong pipeline dùng `LocalSearcher`; bỏ "BM25 tạm"
- [ ] M13-T6 `RelatedSearch` (BR-10.4) chuyển sang `LocalSearcher`

## Kiểm thử

- [ ] Unit RRF + boost
- [ ] Unit cắt ngân sách
- [ ] Tích hợp khoản đã bãi bỏ nằm ở notices, không ở contexts
- [ ] Tích hợp degraded (embedding lỗi / ES lỗi)
- [ ] `assert_invariant()` trên mọi kết quả
- [ ] M13-T7 Golden Q2, Q4

## Tiêu chí chấp nhận (F11 §7)

- [ ] Q2: ngữ cảnh có quy định hiện hành về HĐĐT khởi tạo từ máy tính tiền cho hộ kinh doanh (NĐ 123 sửa đổi bởi NĐ 70)
- [ ] Q4: với ngày `2025-03-15`, mọi ngữ cảnh có `hieu_luc_tu <= 2025-03-15 < hieu_luc_den`; dùng TT 78/2021, không dùng TT 32/2025
- [ ] Không ngữ cảnh `chinh` nào hết hiệu lực tại ngày áp dụng (kiểm tra tự động trên bộ đánh giá)
- [ ] p95 ≤ 1.5 s

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Golden Q1 vẫn đạt mục "≥ 1 quy định thay thế gợi ý" sau khi đổi `RelatedSearch`
