# M06 – Hợp nhất phiên bản (cơ bản) · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F06](../../features/F06-hop-nhat-phien-ban.md)

## Chuẩn bị

- [ ] Ứng viên NĐ 70 và TT 32 đã duyệt (M05), có cạnh `SUA_DOI` / `BAI_BO` / `THAY_THE` trong Neo4j
- [ ] Duyệt bổ sung bảng `index_outbox`
- [ ] Chốt cách xử lý sửa đổi cả Điều có nhiều khoản (plan §6)

## Triển khai

- [ ] M06-T1 Migration `consolidation_run`, `index_outbox`
- [ ] M06-T2 Chuẩn hóa phạm vi: Điểm → Khoản cha, Điều → các Khoản, `so_hieu` → owner của văn bản + đích của cạnh đi ra
- [ ] M06-T2 Chỉ đọc cạnh đã duyệt; ghép `noi_dung_moi`, `thu_tu_trong_nguon` từ `relation_candidate`
- [ ] M06-T3 `rebuild_versions` thuần: sắp `(tu_ngay, ngày ban hành nguồn, thu_tu)`
- [ ] M06-T3 `SUA_DOI` cả khoản: đóng bản hiện tại, mở bản mới `SUA_DOI`, `nguon_sua_doi`
- [ ] M06-T3 `BAI_BO` khoản / Điều cha: đóng bản hiện tại, không bản kế
- [ ] M06-T3 Cùng ngày khác nguồn → `conflict`, bỏ qua owner
- [ ] M06-T3 Đã bãi bỏ rồi còn sự kiện → `TARGET_ALREADY_REPEALED`
- [ ] M06-T3 Sự kiện cấp điểm / `BO_SUNG` → `NOT_SUPPORTED_YET`
- [ ] M06-T4 Diff theo `id` + `content_hash`; giữ embedding khi nội dung không đổi; bản mới / đổi → `embedding_stale = true`
- [ ] M06-T4 Ghi `index_outbox` cho `upsert` / `delete`
- [ ] M06-T5 `THAY_THE`: `VanBan(cũ).hieu_luc_den`, đóng mọi phiên bản đang mở
- [ ] M06-T5 `trang_thai` văn bản theo BR-06.10, dùng `today_vn()`
- [ ] M06-T6 Văn bản liên quan → `CONSOLIDATED`; ghi `consolidation_run`; `enqueue("index")`
- [ ] M06-T7 Truy vấn bất biến (chồng lấn, đứt quãng, `tu >= den`)
- [ ] M06-T8 `POST /consolidation/runs`, `GET /consolidation/runs/{id}`, `GET /units/versions`

## Kiểm thử

- [ ] Unit `rebuild` đủ 8 ca ở plan §5
- [ ] Property-based: chuỗi luôn liên tiếp, không chồng lấn, xác định
- [ ] Tích hợp NĐ 123 sau NĐ 70: Đ3 K10 và Đ19 K1 đúng
- [ ] Tích hợp thu hồi cạnh → phiên bản biến mất + outbox `delete`
- [ ] Tích hợp `APP_FAKE_TODAY=2025-03-15` → trạng thái văn bản đúng

## Tiêu chí chấp nhận (F06 §7)

- [ ] `123/2020/NĐ-CP:Đ3:K10` có đúng 1 phiên bản `[2022-07-01, 2025-06-01)`
- [ ] Không điều khoản nào có hai phiên bản chồng lấn (truy vấn bất biến tự động trả 0 dòng)
- [ ] TT 78/2021 có `hieu_luc_den = 2025-06-01`, `trang_thai = het_hieu_luc`
- [ ] Chạy hợp nhất 2 lần liên tiếp → lần 2 `versions_created = 0`, `versions_deleted = 0`

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Truy vấn bất biến chạy trong CI trên đồ thị fixture
