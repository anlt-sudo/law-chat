# M03 – Tách cấu trúc & ghi đồ thị · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F03 – Tách cấu trúc văn bản](../../features/F03-tach-cau-truc.md) |
| Giai đoạn | PoC – tuần 2 |
| Ước lượng | 4–5 ngày |
| Phụ thuộc | M02 |
| Module dùng kết quả | M04 (quoted_blocks, parser tham chiếu), M06, M07, M09 (alias), M15 (V5) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Từ văn bản chuẩn hóa, **chỉ bằng regex / parser** (không LLM), dựng cây `VanBan → Chuong → Dieu → Khoan → Diem` trong Neo4j với ID xác định, metadata và ngày hiệu lực, phiên bản `GOC` cho mỗi Khoản (hoặc Điều không khoản), khối trích dẫn cho M04. Đồng thời xây gói `app/legal` dùng chung: nhãn hiển thị và parser tham chiếu dạng chữ.

## 2. Phạm vi

| Trong M03 | Để sau |
|---|---|
| Toàn bộ F03 (BR-03.1 → BR-03.17) | Gán chủ đề / đối tượng (M04, M11) |
| Parser tham chiếu dạng chữ `khoản 4 Điều 9 Nghị định 123/2020` → ID | Kiểm tra trích dẫn V5 (M15 dùng lại parser này) |
| API cấu trúc, parse report, sửa metadata | Chạy lại hợp nhất khi sửa metadata (handler `consolidate` có ở M06; M03 chỉ enqueue) |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/legal/
├── ids.py              # (M00) build / parse ID
├── labels.py           # label("…:Đ3:K10") → "khoản 10 Điều 3 Nghị định 123/2020/NĐ-CP"
├── doc_types.py        # suy loại + cơ quan từ hậu tố số hiệu (BR-03.2, BR-03.3)
├── aliases.py          # sinh alias[] (BR-03.17)
└── refs.py             # parse_refs(text, context) → list[UnitRef] (dùng ở M04, M09, M15)
backend/app/parsing/
├── metadata.py         # số hiệu, loại, cơ quan, ngày ban hành, trích yếu (BR-03.1 → 03.4)
├── effective_date.py   # ngày hiệu lực văn bản + từng phần (BR-03.5 → 03.7)
├── structure.py        # máy trạng thái theo dòng → cây ParsedUnit (BR-03.9 → 03.12)
├── quoted.py           # nhận diện khối “…” sau "như sau:" (BR-03.11)
├── continuity.py       # kiểm tra liên tục (BR-03.14)
├── versions.py         # dựng PhienBan GOC, content_hash (BR-03.15, 03.16)
├── graph_writer.py     # ghi Neo4j trong 1 transaction (MERGE, xóa node thừa)
├── models.py           # ORM parse_result, metadata_audit; Pydantic ParsedDocument, ParsedUnit
├── runner.py           # handler job "parse"
└── router.py           # /api/v1/documents..., /ingest/source-documents/{id}/parse
```

### 3.2. Máy trạng thái tách cấu trúc

```python
class ParsedUnit(BaseModel):
    id: str; label: Literal["Chuong","Dieu","Khoan","Diem"]
    so: str; tieu_de: str | None; thu_tu: int
    parent_id: str; text_lines: list[str]
    noi_dung_trich: list[str] = []    # khối “…” thuộc unit này
```

| Trạng thái | Sự kiện dòng | Hành động |
|---|---|---|
| `PREAMBLE` (trước Điều đầu tiên) | `^Chương\s+([IVXLC]+)` | mở Chương, dòng kế (in hoa) là tiêu đề |
| | `^Điều\s+(\d+[a-z]?)\.\s*(.*)` | mở Điều → `IN_DIEU` |
| | dòng đánh số `1.` / `a)` | **bỏ qua** (thuộc "Căn cứ" – BR-03.10) |
| `IN_DIEU` | `^Mục\s+\d+` | ghi chú, không tạo node |
| | `^(\d+[a-z]?)\.\s+` | mở Khoản (đóng Điểm đang mở) |
| | `^([a-zđ]\d?)\)\s+` | mở Điểm trong Khoản hiện tại (không có Khoản → cảnh báo, gắn vào Điều) |
| | dòng kết thúc bằng `như sau:` và dòng kế bắt đầu `“` | → `IN_QUOTE` |
| | `PHỤ LỤC` | → `APPENDIX` |
| | nội dung khác | nối vào unit đang mở |
| `IN_QUOTE` | dòng có `”` đóng (đếm cân bằng `“` / `”`) | kết thúc khối, lưu vào `noi_dung_trich` của unit đang mở → `IN_DIEU` |
| | dòng khác (kể cả `Điều 9.`, `1.`, `a)`) | gom vào khối, **không** mở node (BR-03.11) |
| `APPENDIX` | – | không tạo Khoản / Điểm (BR-03.10) |

Lưu ý: dấu ngoặc kép trong văn bản có thể là `“ ”` hoặc `"`; F02 giữ nguyên ký tự nên parser nhận cả hai, ưu tiên `“ ”`. Khối trích dẫn nhiều đoạn (mỗi đoạn mở `“` riêng) vẫn thuộc cùng câu dẫn cho tới khi gặp unit mới ngoài ngoặc.

### 3.3. Ngày hiệu lực

| Mẫu (BR-03.5) | Kết quả |
|---|---|
| `có hiệu lực (thi hành) (kể) từ ngày dd tháng mm năm yyyy` | ngày đó |
| `… từ ngày dd/mm/yyyy` | ngày đó |
| `… kể từ ngày ký` / `… từ ngày ký ban hành` | `ngay_ban_hanh` |
| `… sau N ngày kể từ ngày ký` | `ngay_ban_hanh + N ngày` |
| Hiệu lực riêng: `(Khoản 3 Điều 5 / Điều 7 / Các quy định tại …) có hiệu lực (thi hành) từ ngày …` | `hieu_luc_rieng: [{unit_ids, tu_ngay}]`, ghi đè `hieu_luc_tu` cho PhienBan GOC của các unit (dùng `refs.parse_refs`) |

Tìm trong Điều có tiêu đề chứa "Hiệu lực" (ưu tiên), không có thì quét 3 Điều cuối. Không thấy → `hieu_luc_tu = NULL`, `NEEDS_ATTENTION` (BR-03.7).

### 3.4. Parser tham chiếu `legal/refs.py`

```python
class RefContext(BaseModel):
    current_so_hieu: str            # "Nghị định này", "Điều này" → văn bản hiện tại (BR-04.5)
    default_target_so_hieu: str | None = None   # kế thừa từ tiêu đề Điều (BR-04.4)
    current_dieu: str | None = None

class UnitRef(BaseModel):
    text: str; span: tuple[int, int]
    so_hieu: str | None; dieu: str | None; khoan: str | None; diem: str | None
    unit_id: str | None              # None khi thiếu văn bản
```

- Nhận: `điểm a khoản 4 Điều 9`, `khoản 10 Điều 3 Nghị định số 123/2020/NĐ-CP`, `Điều 5, Điều 6 và Điều 7`, `từ Điều 5 đến Điều 7`, `khoản 10 Điều 3, khoản 2 Điều 5` (BR-04.6), `Thông tư số 78/2021/TT-BTC`.
- Số hiệu rút gọn trong văn bản (`Nghị định số 123/2020/NĐ-CP` luôn đầy đủ trong văn bản pháp luật) – chỉ cần số hiệu đầy đủ; rút gọn kiểu người dùng gõ do M09 xử lý bằng alias.

### 3.5. Ghi Neo4j

| Quyết định | Chi tiết |
|---|---|
| **(bổ sung)** Label phụ `:DonVi` | Mọi Chuong / Dieu / Khoan / Diem có thêm label `DonVi` + constraint `donvi_id` để các truy vấn theo ID không label (F06 §6.1, F13 §6.1) dùng được index. Thêm vào `neo4j_schema.ensure()` |
| Không phụ thuộc APOC | Ghi theo từng label bằng `UNWIND $rows AS r MERGE (n:Dieu:DonVi {id: r.id}) SET n += r.props` (4 truy vấn), rồi một truy vấn `MERGE (p)-[:CO {thu_tu}]->(n)` |
| Transaction | Toàn bộ văn bản trong 1 write transaction (văn bản lớn ~ vài nghìn node – chấp nhận được ở dev) |
| Tách lại | Node của văn bản **không còn** trong lần tách mới → xóa nếu không có cạnh `SUA_DOI` / `BAI_BO` / `VIEN_DAN` / `HUONG_DAN` trỏ tới; có cạnh → giữ, ghi cảnh báo `ORPHAN_REFERENCED` |
| PhienBan GOC | `MERGE (p:PhienBan {id: "<unit>@<tu>"})`; nếu `hieu_luc_tu` đổi (sửa metadata) thì ID đổi → xóa bản GOC cũ của unit trước khi tạo mới. `content_hash = sha256(noi_dung NFC)` |
| `hieu_luc_tu = NULL` | ID tạm `<unit>@unknown`, `hieu_luc_tu = NULL` → F13 coi là `khong_xac_dinh` (BR-13.4) |
| `VanBan.trang_thai` | Tạm tính theo `hieu_luc_tu` / hôm nay; M06 tính lại đầy đủ |

### 3.6. Schema PostgreSQL (migration `0004_parsing`)

`parse_result`, `metadata_audit` đúng F03 §6.2.

### 3.7. API

Theo F03 §5. `PATCH /documents/{slug}/metadata`:
- Trường được sửa: `so_hieu`, `loai`, `trich_yeu`, `ngay_ban_hanh`, `hieu_luc_tu`, `hieu_luc_den`, `hieu_luc_hoi_to`, `ly_do` (bắt buộc).
- Kiểm tra `hieu_luc_tu >= ngay_ban_hanh` trừ khi `hieu_luc_hoi_to = true`.
- Ghi `metadata_audit` từng trường; cập nhật PhienBan GOC; trạng thái `NEEDS_ATTENTION → PARSED`; nếu văn bản đã từng `CONSOLIDATED` → `enqueue("consolidate", {"so_hieu": …})`, trả `reconsolidate: true`.
- `GET /documents` ở M03 lọc `loai`, `co_quan`, `trang_thai`, `q`; lọc `chu_de` thêm ở M04.

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M03-T1 | `legal/doc_types.py`, `labels.py`, `aliases.py` | Loại / cơ quan từ hậu tố; nhãn tiếng Việt cho mọi cấp ID; alias | 03.2, 03.3, 03.17 | 0.5 ngày |
| M03-T2 | `parsing/metadata.py` | Số hiệu, ngày ban hành, trích yếu (dòng in hoa sau tên loại), đối chiếu `metadata_nguon` | 03.1, 03.4, 03.8 | 0.5 ngày |
| M03-T3 | `structure.py` + `quoted.py` | Máy trạng thái 3.2 | 03.9–03.12 | 1 ngày |
| M03-T4 | `continuity.py` | Cảnh báo nhảy số Điều / Khoản / Điểm | 03.14 | 0.25 ngày |
| M03-T5 | `legal/refs.py` | Parser tham chiếu 3.4 (dùng ngay cho hiệu lực riêng) | 03.6, 04.4–04.6 | 0.75 ngày |
| M03-T6 | `effective_date.py` | 3.3 | 03.5–03.7 | 0.5 ngày |
| M03-T7 | `versions.py` | PhienBan GOC, nội dung Khoản gồm câu dẫn + toàn bộ Điểm, `diem[]` | 03.15, 03.16 | 0.25 ngày |
| M03-T8 | `graph_writer.py` + constraint `DonVi` | 3.5 | 03.13 | 0.5 ngày |
| M03-T9 | Migration + runner job `parse` | Lỗi `NO_SO_HIEU` / `NO_STRUCTURE` → `FAILED`; thành công → `PARSED`, lưu `parse_result` (stats, warnings, quoted_blocks, hieu_luc_rieng), `enqueue("extract")` | – | 0.25 ngày |
| M03-T10 | API | 3.7 | – | 0.5 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit `structure` | Đoạn mẫu có "Căn cứ" đánh số → không sinh Khoản; Điều không chia khoản; Điểm `đ`; Điều `9a` |
| Unit `quoted` | Khoản NĐ 70 "Sửa đổi, bổ sung Điều 9 như sau: “Điều 9. … 1. … a) …”" → NĐ 70 chỉ có 1 Khoản, khối trích chứa `Điều 9.` |
| Unit `effective_date` | Đủ 4 mẫu BR-03.5 + hiệu lực riêng NQ 198 |
| Unit `refs` | Bảng ca kiểm thử: đơn, liệt kê, khoảng, "Nghị định này", kế thừa đích mặc định |
| Unit `labels` | `…:Đ9:K4:a` → "điểm a khoản 4 Điều 9 Nghị định 123/2020/NĐ-CP" |
| Golden | Mỗi văn bản fixture → snapshot `stats` (số chương / điều / khoản / điểm) so với `manifest.yaml`; thay đổi parser làm đổi snapshot phải được review |
| Tích hợp | Tách 2 lần → `MATCH (n:DonVi) RETURN count(n)` không đổi; sửa fixture bỏ 1 Điều → node thừa bị xóa |
| Tích hợp | PATCH metadata: `hieu_luc_tu < ngay_ban_hanh` không có cờ hồi tố → 422; hợp lệ → audit + trạng thái `PARSED` |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Văn bản có định dạng lệch chuẩn (khoản viết `1)`, điều thiếu dấu chấm) | Regex cấu hình được; cảnh báo liên tục giúp phát hiện; golden test theo fixture |
| Dấu ngoặc trích dẫn không cân bằng | Khối mở mà không đóng tới hết Điều → đóng tại ranh giới Điều kế + cảnh báo `UNBALANCED_QUOTE` |
| Phụ lục chứa bảng biểu dài | PoC: phụ lục chỉ lưu trong file normalized, không vào đồ thị và không tách Khoản. Nếu câu hỏi đánh giá cần nội dung phụ lục thì bổ sung ở M11 |
| ID PhienBan đổi khi sửa `hieu_luc_tu` | Đã xử lý ở 3.5; M06 rebuild sau đó |

## 7. Bàn giao

- `parse_result.quoted_blocks = [{"unit_id", "text", "seq"}]` – M04 nối khối trích với câu dẫn theo `unit_id` + `seq`.
- `legal/refs.parse_refs` và `legal/labels.label` là API dùng chung, không viết lại ở module khác.
- Mọi node cấu trúc có label `:DonVi`; module sau truy vấn theo `(:DonVi {id: …})`.
