# M04 – Trích xuất quan hệ (luật mẫu) & danh mục · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F04 – Trích xuất quan hệ](../../features/F04-trich-xuat-quan-he.md) – tầng 1 (luật mẫu) |
| Giai đoạn | PoC – tuần 3 |
| Ước lượng | 3–4 ngày |
| Phụ thuộc | M03 (cây cấu trúc, `quoted_blocks`, `legal/refs.py`), M01 (chỉ để M11 cắm LLM vào sau) |
| Module dùng kết quả | M05, M06, M10, M11 (tầng LLM), M16 (liên kết lại) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Phát hiện quan hệ `SUA_DOI`, `BAI_BO`, `THAY_THE`, `HUONG_DAN`, `VIEN_DAN` bằng luật mẫu câu, liên kết tham chiếu về đúng ID, lưu thành ứng viên trong PostgreSQL. Cạnh rủi ro thấp ghi thẳng vào đồ thị; cạnh rủi ro cao chờ duyệt. Gán chủ đề / đối tượng bằng từ khóa và seed danh mục có kiểm soát.

## 2. Phạm vi

| Trong M04 | Để M11 |
|---|---|
| Tầng 1: 7 luật mẫu F04 §1.2 | Tầng 2 LLM (`extract_relations`) cho câu khó |
| Câu có từ khóa kích hoạt nhưng luật không khớp đủ → ứng viên `manual_required` (fallback BR-04.3), đếm tỷ lệ | LLM phân loại chủ đề / đối tượng cho Điều không khớp từ khóa |
| Liên kết tham chiếu BR-04.4 → BR-04.10 | |
| Độ tin cậy + trạng thái BR-04.11 → BR-04.13 | |
| `THUOC_CHU_DE`, `AP_DUNG_CHO` theo **từ khóa** (BR-04.15 phần đầu) | |
| Danh mục `ChuDe`, `DoiTuong` + API | |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/relations/
├── models.py          # ORM relation_candidate; Pydantic Candidate, RuleMatch
├── sentences.py       # tách câu theo Điều / Khoản, mang ngữ cảnh tiêu đề Điều (BR-04.4)
├── rules/
│   ├── base.py        # Rule Protocol: match(sentence, ctx) → list[RuleMatch]
│   ├── sua_doi.py     # R-SD-01, R-SD-02
│   ├── bai_bo.py      # R-BB-01, R-BB-02
│   ├── thay_the.py    # R-TT-01
│   ├── huong_dan.py   # R-HD-01
│   └── vien_dan.py    # R-VD-01
├── triggers.py        # từ khóa kích hoạt (BR-04.2)
├── resolve.py         # RuleMatch → dich_unit_id; kiểm tra tồn tại trong Neo4j (BR-04.7, 04.8)
├── content.py         # gắn noi_dung_moi từ quoted_blocks (BR-04.9)
├── confidence.py      # BR-04.11
├── topics.py          # gán ChuDe / DoiTuong bằng từ khóa (BR-04.14, 04.15)
├── graph_writer.py    # ghi cạnh tu_dong_duyet; THUOC_CHU_DE, AP_DUNG_CHO {nguon:'rule'}
├── runner.py          # handler job "extract"
└── router.py          # /ingest/documents/{slug}/extract-relations, /relation-candidates, /taxonomy
backend/app/taxonomy/
├── seed.yaml          # chủ đề + đối tượng + từ khóa (BR-04.14)
└── service.py         # nạp seed vào Neo4j (MERGE), CRUD
```

### 3.2. Tách câu và ngữ cảnh

- Đơn vị xử lý: mỗi Khoản (hoặc Điều không khoản) của văn bản nguồn; câu dẫn là phần trước khối trích dẫn. Khối trích dẫn **không** chạy luật (đó là nội dung mới của văn bản khác).
- `SentenceCtx`: `nguon_unit_id`, `current_so_hieu`, `default_target_so_hieu` (từ tiêu đề Điều dạng "Sửa đổi, bổ sung một số điều của Nghị định số 123/2020/NĐ-CP"), `thu_tu_trong_nguon` (thứ tự tăng dần trong văn bản), `quoted_block_ids` liền sau.
- Câu dẫn dạng "a) Sửa đổi điểm a khoản 4 như sau:" bên trong khoản "4. Sửa đổi, bổ sung Điều 9 như sau:" → kế thừa `Điều 9` từ cấp trên (ngữ cảnh lồng 2 tầng).

### 3.3. Luật mẫu

| Luật | Regex chính (rút gọn, không phân biệt hoa thường) | Ra |
|---|---|---|
| R-SD-01 | `^(?:\w+[.)]\s*)?sửa đổi(?:,\s*bổ sung)?\s+(?P<ref>.+?)\s+như sau:?$` | `SUA_DOI/SUA_DOI` × mỗi ref |
| R-SD-02 | `bổ sung\s+(?P<ref>(?:điểm|khoản|Điều)\s+\S+)\s+(?:vào\s+)?(?:sau\s+)?(?P<anchor>.+?)\s+như sau` | `SUA_DOI/BO_SUNG`, đích là ID mới (BR-04.8) |
| R-BB-01 | `bãi bỏ\s+(?P<ref>.+?)[.;]?$` | `BAI_BO` × mỗi ref |
| R-BB-02 | `(?P<doc>(?:Nghị định|Thông tư|Quyết định)\s+số\s+\S+)\s+hết hiệu lực(?: thi hành)?\s+kể từ ngày` | `THAY_THE` (văn bản nguồn thay thế văn bản `doc`) |
| R-TT-01 | `thay thế\s+(?P<doc>(?:Nghị định|Thông tư|Quyết định)\s+số\s+\S+)` | `THAY_THE` |
| R-HD-01 | `(?:Thông tư này\s+)?(?:quy định chi tiết|hướng dẫn)(?: thi hành)?\s+.*?(?P<doc>(?:Nghị định|Luật)\s+số\s+\S+)` | `HUONG_DAN` (cấp văn bản; có Điều → cấp Điều) |
| R-VD-01 | `theo quy định tại\s+(?P<ref>.+?)(?=[,.;]|$)` | `VIEN_DAN` |

`ref` được giao cho `legal/refs.parse_refs(ref, ctx)` → 1..n `UnitRef` (BR-04.6). Luật được kiểm thử bằng bảng câu mẫu thật lấy từ NĐ 70, TT 32 (mỗi luật ≥ 5 câu khớp + ≥ 3 câu không được khớp).

**Quyết định cần duyệt:** R-BB-02 nói về văn bản khác hết hiệu lực. Schema `BAI_BO` chỉ cho Khoản / Điều làm đích, nên PoC mã hóa thành `THAY_THE` cấp văn bản khi văn bản nguồn cùng loại và cùng lĩnh vực; nếu không có văn bản thay thế thì tạo ứng viên `manual_required` kèm cảnh báo `DOC_LEVEL_REPEAL` để biên tập viên quyết định.

### 3.4. Liên kết, nội dung, độ tin cậy

| Bước | Quy tắc |
|---|---|
| Tồn tại đích (BR-04.7) | `MATCH (:VanBan {so_hieu})` không có → `cho_van_ban_dich`, `dich_unit_id = NULL`, lưu `dich_so_hieu` + tham chiếu chữ trong `canh_bao` để M16 liên kết lại. Có văn bản nhưng không có `(:DonVi {id})` và không phải `BO_SUNG` → `dich_khong_ton_tai`, conf ≤ 0.5 |
| `noi_dung_moi` (BR-04.9) | `SUA_DOI`: lấy quoted block liền sau câu dẫn (cùng `unit_id`, `seq` kế tiếp); bỏ `“ ”` bao ngoài; thiếu → `THIEU_NOI_DUNG` |
| `tu_ngay` (BR-04.10) | `hieu_luc_tu` của văn bản nguồn; có `hieu_luc_rieng` chứa `nguon_unit_id` → dùng ngày riêng |
| Độ tin cậy (BR-04.11) | Đích tường minh (ref có số hiệu) = 0.95; kế thừa ngữ cảnh = 0.85; đích không tồn tại = min(·, 0.5); `manual_required` = 0 |
| Trạng thái (BR-04.12, 04.13) | `SUA_DOI` / `BAI_BO` / `THAY_THE` → `cho_duyet` (trừ 2 trạng thái đích ở trên); `HUONG_DAN` / `VIEN_DAN` / `AP_DUNG_CHO` / `THUOC_CHU_DE` → `tu_dong_duyet` + ghi Neo4j ngay |

### 3.5. Chạy lại (API extract-relations)

- Ứng viên `da_duyet` / `tu_choi` / `tu_dong_duyet` đã có giữ nguyên. So khớp ứng viên mới với cũ theo khóa `(nguon_unit_id, loai, dich_unit_id hoặc dich_so_hieu, kieu)`; trùng → bỏ qua; ứng viên cũ `cho_duyet` không còn sinh ra → xóa.
- Cạnh `tu_dong_duyet` ghi bằng `MERGE … {candidate_id}` nên chạy lại không trùng.

### 3.6. Chủ đề / đối tượng

- `seed.yaml`: 4 chủ đề, 5 đối tượng theo BR-04.14, mỗi mục có `tu_khoa[]` (vd `hoa_don_dien_tu: [hóa đơn điện tử, hóa đơn khởi tạo từ máy tính tiền, mã của cơ quan thuế]`).
- Khớp từ khóa trên tiêu đề + nội dung GOC của Điều (so sánh không dấu, lowercase) → `THUOC_CHU_DE {nguon:'rule'}` / `AP_DUNG_CHO {nguon:'rule'}`. Văn bản nhận chủ đề có ≥ 20% số Điều.
- Ghi vào `relation_candidate` với `loai = THUOC_CHU_DE / AP_DUNG_CHO`, `tu_dong_duyet` (để rà soát được trên giao diện duyệt).

### 3.7. Schema & API

- Migration `0005_relations`: `relation_candidate` đúng F04 §6.1.
- API theo F04 §5. `GET /documents` bổ sung lọc `chu_de`.

### 3.8. Kết thúc job

Có ứng viên `cho_duyet` → `IN_REVIEW`; không có → `REVIEWED` + `enqueue("consolidate", {"so_hieu": …})` (handler có ở M06). Ghi `stats`: số câu, số câu khớp luật, số câu `manual_required`, **tỷ lệ câu cần LLM**.

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M04-T1 | Bộ câu mẫu | Trích ≥ 60 câu thật từ NĐ 70, TT 32, NQ 198 + kỳ vọng (loại, đích, kiểu) → `tests/fixtures/relation_sentences.yaml` | – | 0.5 ngày |
| M04-T2 | Migration + ORM | `relation_candidate` | – | 0.25 ngày |
| M04-T3 | `sentences.py` | 3.2, ngữ cảnh lồng 2 tầng | 04.4, 04.5 | 0.5 ngày |
| M04-T4 | 7 luật mẫu + triggers | 3.3 | 04.1, 04.2 | 1 ngày |
| M04-T5 | `resolve`, `content`, `confidence` | 3.4 | 04.6–04.13 | 0.5 ngày |
| M04-T6 | Taxonomy + topics | 3.6, seed Neo4j `ChuDe`, `DoiTuong` | 04.14, 04.15 | 0.5 ngày |
| M04-T7 | Runner + graph writer + chạy lại | 3.5, 3.8 | 04.12, 04.13 | 0.5 ngày |
| M04-T8 | API | `/relation-candidates`, `/taxonomy/*`, `extract-relations` | – | 0.25 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit (tham số hóa) | Chạy toàn bộ `relation_sentences.yaml`: precision / recall từng luật; mục tiêu precision ≥ 0.95 cho luật `SUA_DOI` / `BAI_BO` |
| Unit | Kế thừa ngữ cảnh: khoản "Sửa đổi khoản 4 Điều 9" trong Điều sửa đổi NĐ 123 → `123/2020/NĐ-CP:Đ9:K4` |
| Unit | Liệt kê "Bãi bỏ khoản 10 Điều 3, khoản 2 Điều 5" → 2 ứng viên; "từ Điều 5 đến Điều 7" → 3 |
| Tích hợp | NĐ 70 trên đồ thị có NĐ 123 → ứng viên `BAI_BO` đích `…:Đ3:K10`, conf 0.95, `tu_ngay = 2025-06-01` |
| Tích hợp | NĐ 70 khi **chưa** nạp NĐ 123 → ứng viên `cho_van_ban_dich` |
| Tích hợp | Chạy lại sau khi duyệt 1 ứng viên → ứng viên đã duyệt giữ nguyên, không sinh trùng cạnh |
| Đo | Tỷ lệ câu `manual_required` trên bộ PoC (mục tiêu ≤ 20%) |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Văn bản sửa đổi diễn đạt đa dạng | Bộ câu mẫu thật trước khi viết regex; câu không khớp → `manual_required`, không mất thông tin |
| Sai đích do kế thừa ngữ cảnh | Conf 0.85 → luôn được duyệt tay (không vào bulk-approve ≥ 0.95) |
| Tỷ lệ cần LLM > 20% | Ghi danh sách câu để M11 ưu tiên; có thể thêm luật mẫu |
| Nhiều ứng viên `manual_required` vượt ngân sách duyệt 2 giờ/tuần | Theo dõi số lượng sau M04; báo trước khi bắt đầu M05 |

## 7. Bàn giao

- M05 đọc `relation_candidate` trạng thái `cho_duyet`, `dich_khong_ton_tai`, `manual_required`.
- M11 cắm tầng LLM vào `runner` tại điểm "câu có trigger, luật không khớp đủ" – thay `manual_required` bằng lời gọi `extract_relations`.
- M16 dùng chỉ mục `relation_candidate (dich_so_hieu) WHERE trang_thai = 'cho_van_ban_dich'` để liên kết lại.
