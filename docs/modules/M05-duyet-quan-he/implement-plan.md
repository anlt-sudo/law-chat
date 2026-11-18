# M05 – Duyệt quan hệ · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F05 – Duyệt quan hệ](../../features/F05-duyet-quan-he.md) |
| Giai đoạn | PoC – tuần 3 |
| Ước lượng | 3 ngày (2 ngày API, 1 ngày giao diện tối giản) |
| Phụ thuộc | M04 |
| Module dùng kết quả | M06, M10 (dùng lại khung frontend), M16, M17 (độ chính xác cạnh) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Biên tập viên duyệt mọi cạnh `SUA_DOI`, `BAI_BO`, `THAY_THE` trước khi chúng ảnh hưởng câu trả lời, trong ngân sách chuyên gia **2 giờ/tuần**. Chỉ cạnh `da_duyet` được ghi vào Neo4j và kích hoạt hợp nhất.

## 2. Phạm vi

| Trong M05 | Để sau |
|---|---|
| Toàn bộ API F05 §5 | Thống kê nâng cao, biểu đồ (MVP, M10 đợt 2) |
| Kiểm tra hợp lệ, xung đột, duyệt hàng loạt, thêm thủ công, thu hồi | |
| **(bổ sung)** Khung frontend `frontend/` + trang duyệt tối giản | Trang chat, văn bản (M10) |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/relations/review/
├── models.py        # ORM review_action; Pydantic ApproveRequest, CandidateDetail, BulkResult
├── queue.py         # truy vấn hàng đợi + sắp xếp BR-05.2
├── validate.py      # BR-05.4 (a–d), BR-05.5 xung đột
├── diff.py          # diff ký tự / từ giữa nội dung hiện hành và noi_dung_moi
├── service.py       # approve / reject / bulk / manual_add / revoke; ghi Neo4j; BR-05.8
├── stats.py         # /review/stats
└── router.py        # /api/v1/review/...
frontend/                      # (bổ sung) tạo ở M05, M10 mở rộng
├── package.json               # Vite + React 18 + TypeScript
├── src/api/client.ts          # fetch kèm X-API-Key (lấy từ localStorage)
├── src/pages/ReviewQueue.tsx
├── src/pages/ReviewCandidate.tsx
└── src/components/DiffView.tsx
```

### 3.2. Hàng đợi (BR-05.2)

```sql
SELECT rc.*
FROM relation_candidate rc
WHERE rc.trang_thai IN ('cho_duyet','dich_khong_ton_tai')   -- gồm cả manual_required (trang_thai = cho_duyet)
  AND (:document IS NULL OR rc.source_document_id = :document)
  AND (:loai IS NULL OR rc.loai = :loai)
  AND (:max_conf IS NULL OR rc.confidence <= :max_conf)
ORDER BY rc.confidence ASC, <hiệu lực văn bản nguồn> ASC, rc.thu_tu_trong_nguon ASC;
```

Hiệu lực văn bản nguồn lấy từ Neo4j một lần cho danh sách văn bản trong trang (hoặc lưu kèm vào `relation_candidate` khi trích xuất – chọn cách thứ hai nếu đơn giản hơn: thêm cột `nguon_hieu_luc_tu DATE` **(bổ sung)**).

### 3.3. Kiểm tra khi duyệt

| Mã | Kiểm tra | Lỗi |
|---|---|---|
| BR-05.4a | `(:DonVi {id: dich_unit_id})` tồn tại, trừ `kieu = BO_SUNG`; `THAY_THE` → `(:VanBan {so_hieu})` tồn tại | 422 `TARGET_NOT_FOUND` |
| BR-05.4b | `tu_ngay` không rỗng | 422 `MISSING_TU_NGAY` |
| BR-05.4c | `SUA_DOI` phải có `noi_dung_moi` | 422 `MISSING_CONTENT` |
| BR-05.4d | `tu_ngay < ngay_ban_hanh` văn bản nguồn và `confirm_retroactive = false` | 422 `RETROACTIVE_CONFIRM_REQUIRED` |
| BR-05.5 | Có ứng viên `da_duyet` khác: cùng đích, cùng `tu_ngay`, khác `source_document_id` | 409 `EDGE_CONFLICT` + `conflict_candidate_id` |

### 3.4. Ghi dữ liệu và tính nhất quán PG ↔ Neo4j

Không có transaction phân tán, nên thứ tự cố định:

1. PG: `SELECT … FOR UPDATE` ứng viên (chống 2 biên tập viên duyệt cùng lúc).
2. Kiểm tra 3.3.
3. Neo4j: `MERGE (n)-[r:<LOAI> {candidate_id}]->(d) SET r.tu_ngay, r.kieu` – idempotent. Với `BO_SUNG`: đích chưa tồn tại → chỉ lưu ứng viên, cạnh được tạo bởi M06 khi tạo node mới (M06 đọc ứng viên `da_duyet`). **PoC chưa hỗ trợ `BO_SUNG`** (M11); duyệt vẫn được nhưng M06 ghi cảnh báo `NOT_SUPPORTED_YET`.
4. PG: cập nhật ứng viên + `review_action` trong cùng transaction, commit.
5. Nếu bước 4 lỗi sau khi bước 3 thành công → cạnh tồn tại mà ứng viên chưa `da_duyet`: job đối soát `reconcile_edges` (chạy khi khởi động worker + thủ công) xóa cạnh có `candidate_id` không ở trạng thái `da_duyet`.

Thu hồi (BR-05.9): xóa cạnh theo `candidate_id` → ứng viên về `cho_duyet` → `review_action(revoke)` → `enqueue("consolidate", {"unit_ids": [dich]}, dedupe_key=…)`.

### 3.5. Hoàn tất văn bản (BR-05.8)

Sau mỗi hành động: đếm ứng viên bắt buộc (`loai IN (SUA_DOI,BAI_BO,THAY_THE)`, `trang_thai IN (cho_duyet, dich_khong_ton_tai)` + `manual_required`) của `source_document_id`. Bằng 0 → `REVIEWED`, `enqueue("consolidate", {"unit_ids": <các đích đã duyệt>, "so_hieu": <nguồn>})`.

### 3.6. Duyệt hàng loạt (BR-05.6)

- Chỉ nhận ứng viên `phuong_phap = rule` và `confidence ≥ 0.95`; ứng viên khác trong danh sách → `failed` với `NOT_ELIGIBLE`.
- Mỗi ứng viên chạy cùng kiểm tra 3.3; lỗi → vào `failed`, các ứng viên khác vẫn duyệt.
- `review_action.action = bulk_approve`, `elapsed_ms` chia đều.

### 3.7. Thống kê (`/review/stats`)

`{ "remaining": n, "approved": n, "rejected": n, "edited_rate_by_rule": {...}, "reject_rate_by_rule": {...}, "avg_elapsed_ms": x, "elapsed_by_week": [{"week": "2026-W47", "minutes": 74}] }` – theo dõi ngân sách 2 giờ/tuần.

### 3.8. Giao diện tối giản

- `ReviewQueue`: bảng (conf, nguồn → đích, loại, rule), lọc theo văn bản / loại / max_conf, nút "Duyệt hàng loạt (rule, ≥ 0.95)" mở hộp xác nhận liệt kê từng ứng viên.
- `ReviewCandidate`: câu gốc (tô sáng phần khớp luật), nội dung hiện hành của đích, `noi_dung_moi`, diff hai cột, link nguồn; nút **Duyệt**, **Sửa rồi duyệt** (form `loai`, `kieu`, `dich_unit_id`, `tu_ngay`, `noi_dung_moi`), **Từ chối** (bắt buộc lý do); phím tắt `A` / `E` / `R` / `J` (kế tiếp) để duyệt nhanh.
- Đo `elapsed_ms` từ lúc mở ứng viên tới lúc bấm.
- Không cần đăng nhập: ô nhập API key lưu localStorage (bản dev).

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M05-T1 | Migration + ORM | `review_action` (F05 §6), cột `nguon_hieu_luc_tu` (nếu chọn) | 05.7 | 0.25 ngày |
| M05-T2 | Hàng đợi + chi tiết | 3.2; chi tiết kèm phiên bản hiện hành của đích (Neo4j) + diff | 05.2, 05.10 | 0.5 ngày |
| M05-T3 | Validate + xung đột | 3.3 | 05.4, 05.5 | 0.25 ngày |
| M05-T4 | Approve / edit-approve / reject | 3.4, 3.5 | 05.1, 05.3, 05.8 | 0.5 ngày |
| M05-T5 | Bulk, manual add, revoke, reconcile | 3.4, 3.6 | 05.6, 05.9 | 0.5 ngày |
| M05-T6 | Stats | 3.7 | 05.7 | 0.25 ngày |
| M05-T7 | Khung frontend + 2 trang | 3.8 | 05.10 | 1 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit | Validate từng lỗi 3.3 |
| Tích hợp | Ứng viên `cho_duyet` → đồ thị không có cạnh; duyệt → có cạnh `{candidate_id}`; thu hồi → mất cạnh, ứng viên `cho_duyet`, có job `consolidate` |
| Tích hợp | Duyệt hết ứng viên bắt buộc của NĐ 70 → `REVIEWED` + đúng 1 job `consolidate` |
| Tích hợp | Hai ứng viên khác nguồn, cùng đích, cùng ngày → ứng viên thứ hai 409 |
| Tích hợp | Bulk 3 ứng viên, 1 lỗi đích → `approved` 2, `failed` 1 |
| Tích hợp | Lỗi giả lập ở bước ghi PG sau khi ghi Neo4j → `reconcile_edges` xóa cạnh mồ côi |
| Thủ công | Một biên tập viên duyệt toàn bộ NĐ 70 trên giao diện, ghi tổng thời gian |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Ngân sách 2 giờ/tuần (và "0.5 tuần" trong inception §10 chưa rõ) | Bulk-approve; phím tắt; ưu tiên văn bản cần cho Q1–Q5; theo dõi `elapsed_by_week`; làm rõ với chuyên gia trước khi bắt đầu |
| Biên tập viên không phải chuyên gia pháp lý | Mẫu 50 cạnh đã duyệt để chuyên gia rà lại ở M17 (KPI ≥ 99%) |
| Ứng viên `manual_required` thiếu đích / loại | Form "Sửa rồi duyệt" cho nhập đủ trường; validate như ứng viên thường |

## 7. Bàn giao

- M06 nhận job `consolidate` với `unit_ids` và / hoặc `so_hieu`; đọc `noi_dung_moi`, `thu_tu_trong_nguon` từ `relation_candidate` theo `candidate_id` trên cạnh.
- M10 dùng lại `frontend/` (routing, API client, layout).
