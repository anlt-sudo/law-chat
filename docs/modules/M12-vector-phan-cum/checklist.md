# M12 – Vector & phân cụm chủ đề · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F07](../../features/F07-lap-chi-muc.md)

## Chuẩn bị

- [ ] M11 xong: cạnh `THUOC_CHU_DE` / `AP_DUNG_CHO` phủ đủ Điều trong phạm vi
- [ ] bge-m3 nạp trên LM Studio, `embed` trả 1024 chiều
- [ ] Leiden chạy được trên GDS (spike M00-T12)

## Triển khai – embedding

- [ ] M12-T1 Văn bản embedding có tiêu đề ngữ cảnh (BR-07.2)
- [ ] M12-T1 Chỉ embed `embedding_stale = true`; lô 32; `priority = 3`; nhường chat giữa các lô
- [ ] M12-T1 Văn bản dài → cắt đoạn, trung bình, chuẩn hóa L2
- [ ] M12-T1 Ghi `embedding`, `embedding_stale = false`, `embedding_model`
- [ ] M12-T1 LM Studio lỗi → giữ stale, retry, văn bản chưa `INDEXED`
- [ ] M12-T2 Đổi model → đánh dấu toàn bộ stale; đổi số chiều → tạo lại vector index

## Triển khai – phân cụm

- [ ] M12-T3 Chiếu GDS bằng Cypher aggregation, vô hướng, `SUA_DOI` trọng số 2
- [ ] M12-T3 Leiden `includeIntermediateCommunities`, `maxLevels 2`, `randomSeed 42`
- [ ] M12-T3 Ghi `Cum`, `THUOC_CUM`, `CUM_CHA`, `Dieu.cum_id`
- [ ] M12-T3 Gộp cụm < 3 Điều vào láng giềng lớn nhất
- [ ] M12-T3 Giữ ID cụm ổn định (Jaccard ≥ 0.5); xóa cụm cũ không còn; drop projection
- [ ] M12-T4 Điều mới gán vào cụm láng giềng; outbox → `Cum.dirty = true`
- [ ] M12-T5 Tóm tắt cụm dirty: Điều còn hiệu lực hôm nay, ≤ 300 ký tự/Điều, ≤ 6 000 token
- [ ] M12-T5 Hậu kiểm `van_ban_chinh`, `chu_de`, `doi_tuong`; embedding tóm tắt → `tom_tat_embedding`

## Triển khai – runner & API

- [ ] M12-T6 Runner `index` điều phối `bm25` → `embedding` → `communities`
- [ ] M12-T6 `INDEXED` khi đủ ES + không còn stale
- [ ] M12-T6 `/index/status` đủ trường F07 §5
- [ ] M12-T6 `GET /topics`, `GET /topics/{cum_id}`

## Kiểm thử

- [ ] Unit văn bản embedding, cắt văn bản dài
- [ ] Tích hợp stale → 0; sửa 1 khoản chỉ embed phiên bản mới
- [ ] Tích hợp vector query trả kết quả
- [ ] Tích hợp Leiden xác định + ID ổn định; cụm nhỏ bị gộp
- [ ] Tích hợp tóm tắt lọc số hiệu bịa
- [ ] Thủ công đọc tóm tắt cụm trên dữ liệu thật

## Tiêu chí chấp nhận (F07 §7)

- [ ] Sau F06 trên bộ dữ liệu, `phien_ban_stale = 0` và số document ES = số `PhienBan`
- [ ] Mỗi cụm có tóm tắt, `van_ban_chinh` chỉ chứa số hiệu có trong đồ thị
- [ ] Sửa một khoản → chỉ cụm chứa Điều đó được tóm tắt lại

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Ghi lại tham số Leiden đã chọn (`gamma`, số cụm, kích thước trung bình) trong `docs/spikes/leiden.md`
