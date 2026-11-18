# M07 – Lọc hiệu lực & tra cứu trực tiếp · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F13](../../features/F13-loc-hieu-luc.md), [F10](../../features/F10-tra-cuu-truc-tiep.md)

## Chuẩn bị

- [ ] M06 xong trên bộ PoC; truy vấn bất biến trả 0 dòng
- [ ] Đồ thị test tối thiểu (fixture Cypher) cho ma trận F13

## Triển khai – F13

- [ ] M07-T1 `ContextItem`, `Notice`, `RetrievalResult`, `VaiTro` (F10 §6.2)
- [ ] M07-T2 Truy vấn lô trạng thái theo `unit_id` (một truy vấn, `UNWIND`)
- [ ] M07-T2 Khoản / Điều không khoản / Điều có khoản / Điểm / Văn bản theo BR-13.1–13.3
- [ ] M07-T2 Thiếu ngày → `khong_xac_dinh`, không hiệu lực, log `DATA_QUALITY`
- [ ] M07-T2 Nguyên nhân theo thứ tự: `THAY_THE` → `VAN_BAN_HET_HIEU_LUC` → `BAI_BO` → `CHUA_CO_HIEU_LUC` → `KHONG_XAC_DINH`
- [ ] M07-T2 `thay_doi SUA_DOI` cho điều khoản đã sửa; `sap_thay_doi` cho cạnh `tu_ngay > d`
- [ ] M07-T3 `filter()`: loại ngữ cảnh hết hiệu lực → Notice; giữ `lich_su` kèm Notice; thay phiên bản lệch
- [ ] M07-T3 `assert_invariant()` chạy trong test và chế độ dev
- [ ] M07-T6 `POST /effectivity/check`

## Triển khai – F10

- [ ] M07-T4 DIRECT: chuẩn hóa unit_id (Điều → Khoản, Điểm → Khoản cha)
- [ ] M07-T4 Còn hiệu lực → `chinh` + `nguon_sua_doi` + tiêu đề Điều + ≤ 2 Thông tư hướng dẫn
- [ ] M07-T4 Hết hiệu lực → Notice + phiên bản cuối làm `lich_su`
- [ ] M07-T4 `y_dinh = lich_su` → toàn bộ chuỗi phiên bản
- [ ] M07-T4 `RelatedSearch` Protocol + stub
- [ ] M07-T5 GRAPH 2 văn bản (nhóm theo Điều của đích), 1 văn bản (2 chiều), quan hệ cấp văn bản
- [ ] M07-T5 `structured_result` đầy đủ; ngữ cảnh LLM cắt 30 dòng + thống kê
- [ ] M07-T6 `GET /units/lookup`, `GET /documents/{slug}?ngay=`, `GET /documents/{slug}/relations`, `GET /documents/{slug}/amendments?target=`
- [ ] M07-T7 Nối `RelatedSearch` BM25 sau M08

## Kiểm thử

- [ ] Ma trận 11 ca ở plan §5 (kể cả ngày đúng bằng `hieu_luc_den`, hồi tố, thiếu ngày, điểm, phiên bản lệch)
- [ ] Q1 tại hôm nay và tại 2025-03-15
- [ ] Q5 so khớp 100% với cạnh đã duyệt (truy vấn đối chiếu độc lập)
- [ ] Benchmark 50 unit ≤ 100 ms; `/units/lookup` p95 ≤ 200 ms

## Tiêu chí chấp nhận (F13 §7, F10 §7)

- [ ] Bộ test đơn vị: còn hiệu lực, bãi bỏ, sửa đổi, thay thế văn bản, chưa có hiệu lực, hồi tố, ngày bằng `hieu_luc_den` (hết hiệu lực), thiếu ngày
- [ ] Không `ContextItem` `chinh` nào hết hiệu lực lọt qua (bất biến)
- [ ] 50 điều khoản ≤ 100 ms
- [ ] Q1 → Notice `BAI_BO` bởi `70/2025/NĐ-CP:Đ2:K4` từ `2025-06-01` và ≥ 1 quy định thay thế gợi ý còn hiệu lực *(phần gợi ý đạt sau M07-T7)*
- [ ] Q1 với ngày `2025-03-15` → khoản 10 Điều 3 còn hiệu lực, ngữ cảnh `chinh`
- [ ] Q5 → danh sách khớp 100% với cạnh đã duyệt
- [ ] `/units/lookup` p95 ≤ 200 ms

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] Không có chỗ nào khác trong code tự tính hiệu lực ngoài `EffectivityService` và `legal/validity.py`
