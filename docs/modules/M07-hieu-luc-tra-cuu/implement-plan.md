# M07 – Lọc hiệu lực & tra cứu trực tiếp · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F13 – Lọc hiệu lực](../../features/F13-loc-hieu-luc.md), [F10 – Tra cứu trực tiếp](../../features/F10-tra-cuu-truc-tiep.md) |
| Giai đoạn | PoC – tuần 4 |
| Ước lượng | 3–4 ngày |
| Phụ thuộc | M06; M08 cho BR-10.4 (gợi ý quy định thay thế) |
| Module dùng kết quả | M09, M10, M13, M14, M15, M17 |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

- **F13** – dịch vụ dùng chung trả lời "điều khoản / văn bản X có hiệu lực tại ngày d không, nếu không thì vì sao", và lọc mọi ngữ cảnh trước khi đưa cho LLM. Đây là chốt chặn KPI "trích dẫn hết hiệu lực ≤ 1%".
- **F10** – truy xuất `DIRECT` (theo ID tại ngày áp dụng) và `GRAPH` (quan hệ giữa văn bản), cùng các API tra cứu cho giao diện.

## 2. Phạm vi

| Trong M07 | Để sau |
|---|---|
| Toàn bộ F13 | – |
| F10 DIRECT + GRAPH + 5 API | BR-10.4 dùng F11 thật (M13 thay thế bản BM25) |
| Model dùng chung `ContextItem`, `Notice`, `RetrievalResult` | |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/models/retrieval.py     # VaiTro, ContextItem, Notice, RetrievalResult (F10 §6.2)
backend/app/retrieval/
├── effectivity/
│   ├── queries.py      # Cypher lô: trạng thái, nguyên nhân, sửa đổi trước d, thay đổi sau d
│   ├── service.py      # EffectivityService.check(), .filter() (F13 §6.3)
│   ├── explain.py      # thứ tự nguyên nhân F13 §1.2
│   └── router.py       # POST /effectivity/check
├── direct/
│   ├── service.py      # retrieve_direct(unit_ids, ngay, y_dinh) → RetrievalResult
│   ├── graph_mode.py   # retrieve_graph(van_ban[], ngay) → RetrievalResult + structured_result
│   ├── related.py      # RelatedSearch Protocol – BR-10.4; impl BM25 (M08), F11 (M13)
│   └── router.py       # /units/lookup, /documents/{slug}, /relations, /amendments
```

### 3.2. Trạng thái hiệu lực (BR-13.1 → BR-13.4)

Một truy vấn lô cho mọi `unit_id` (BR-13.10):

```cypher
UNWIND $unit_ids AS uid
MATCH (u {id: uid}) WHERE u:DonVi OR u:VanBan
OPTIONAL MATCH (vb:VanBan)-[:CO*]->(u)
WITH uid, u, coalesce(vb, u) AS vb
// owner: Khoản / Điều không khoản; Điều có khoản → các Khoản; Điểm → Khoản cha
CALL {
  WITH u
  OPTIONAL MATCH (u)-[:CO_PHIEN_BAN]->(p1:PhienBan)        RETURN collect(p1) AS own
}
CALL {
  WITH u
  OPTIONAL MATCH (u:Dieu)-[:CO]->(:Khoan)-[:CO_PHIEN_BAN]->(p2:PhienBan) RETURN collect(p2) AS child
}
CALL {
  WITH u
  OPTIONAL MATCH (k:Khoan)-[:CO]->(u:Diem), (k)-[:CO_PHIEN_BAN]->(p3:PhienBan) RETURN collect(p3) AS parent
}
WITH uid, u, vb, own + child + parent AS pbs
RETURN uid, labels(u) AS labels, u.so AS so, vb.so_hieu AS so_hieu,
       vb.hieu_luc_tu AS vb_tu, vb.hieu_luc_den AS vb_den,
       [p IN pbs | {id: p.id, tu: p.hieu_luc_tu, den: p.hieu_luc_den, diem: p.diem,
                    loai: p.loai_thay_doi, nguon: p.nguon_sua_doi}] AS versions
```

Logic quyết định làm ở Python (dễ test hơn Cypher):

| Đơn vị | Có hiệu lực tại `d` khi |
|---|---|
| Khoản / Điều không khoản | ∃ phiên bản `is_active(tu, den, d)` **và** `is_active(vb_tu, vb_den, d)` |
| Điều có khoản | ≥ 1 Khoản có hiệu lực |
| Điểm | Khoản cha có hiệu lực **và** chữ cái điểm ∈ `diem[]` của phiên bản đó |
| Văn bản | `con_hieu_luc` / `het_hieu_luc_mot_phan` / `het_hieu_luc` / `chua_co_hieu_luc` (cùng logic `doc_status` M06 nhưng tại `d`) |
| `hieu_luc_tu` NULL ở bất kỳ cấp | `khong_xac_dinh`, coi như **không** hiệu lực, log `DATA_QUALITY` |

### 3.3. Giải thích nguyên nhân (F13 §1.2)

Truy vấn thứ hai chỉ cho các unit không hiệu lực: cạnh `THAY_THE` tới văn bản chứa, cạnh `BAI_BO` / `SUA_DOI` tới unit / Điều cha / Khoản cha. Xét theo thứ tự: `THAY_THE` → `VAN_BAN_HET_HIEU_LUC` → `BAI_BO` (`tu_ngay <= d`) → `CHUA_CO_HIEU_LUC` (phiên bản đầu `tu > d`) → `KHONG_XAC_DINH` + log. `boi_label` sinh bằng `legal/labels.py`.

Với unit còn hiệu lực: phiên bản hiện hành `loai = SUA_DOI` → `thay_doi = ThayDoi(SUA_DOI, boi = nguon_sua_doi, tu_ngay = pb.tu)` (BR-13.5); có cạnh `tu_ngay > d` → `sap_thay_doi` (BR-13.6).

### 3.4. Lọc ngữ cảnh (BR-13.7 → BR-13.9)

```python
def filter(self, result: RetrievalResult, ngay: date) -> RetrievalResult:
    statuses = self.check([c.unit_id for c in result.contexts], ngay)
    for c in result.contexts:
        s = statuses[c.unit_id]
        if c.vai_tro == VaiTro.lich_su:            # giữ, bắt buộc có Notice
            ensure_notice(s)
        elif s.trang_thai != CON_HIEU_LUC:          # loại, chuyển thành Notice
            drop(c); add_notice(s)
        elif c.phien_ban_id != s.phien_ban_id:      # lệch phiên bản → thay nội dung đúng tại d
            replace_version(c, s.phien_ban_id)
        attach_thay_doi(c, s)
    # thống kê filtered_out, replaced
```

Notice khử trùng theo `unit_id`. Kết quả cuối có **bất biến**: không `ContextItem` nào `vai_tro ≠ lich_su` mà hết hiệu lực tại `d` – thêm `assert_invariant()` chạy trong test và (ở chế độ dev) mỗi lượt hỏi đáp.

### 3.5. DIRECT (F10 §1.1)

1. Chuẩn hóa `unit_id` (BR-10.1).
2. `check()` → có hiệu lực: `ContextItem(chinh, nguon_truy_xuat="direct")` + `nguon_sua_doi` (BR-10.5) + ngữ cảnh phụ: tiêu đề Điều cha, ≤ 2 Thông tư `HUONG_DAN` còn hiệu lực (BR-10.7).
3. Không hiệu lực: `Notice` + phiên bản cuối trước `d` làm `lich_su` (BR-10.3); gọi `RelatedSearch.search(noi_dung_cu, ngay, so_hieu=[văn bản gốc, văn bản gây bãi bỏ, văn bản hướng dẫn], top=3)` → `thay_the_goi_y` (BR-10.4).
4. `y_dinh = lich_su` → thêm toàn bộ chuỗi phiên bản (dùng `/units/versions` của M06) dạng `lich_su` (BR-10.6).
5. Trả `RetrievalResult` (chưa lọc – F08 / M09 gọi `filter` sau, theo BR-08.1 không bỏ qua F13).

`RelatedSearch` ở PoC dùng BM25 (M08) với `query = noi_dung_cu`, lọc `so_hieu` và hiệu lực. Khi M08 chưa xong, dùng stub trả rỗng – Q1 vẫn đạt phần Notice; mục "≥ 1 quy định thay thế" chỉ đạt sau khi nối M08 (M07-T7).

### 3.6. GRAPH (F10 §1.2)

| Trường hợp | Truy vấn |
|---|---|
| 2 văn bản A, B (BR-10.8) | Cạnh `SUA_DOI`/`BAI_BO` từ `(:VanBan {so_hieu:A})-[:CO*]->()` tới `()<-[:CO*]-(:VanBan {so_hieu:B})` (inception §5.4), nhóm theo Điều của B, sắp theo ID |
| 1 văn bản, "A sửa đổi những văn bản nào" (BR-10.9) | Nhóm theo văn bản đích, đếm điều khoản |
| 1 văn bản, "A bị sửa đổi bởi …" | Chiều ngược lại |
| Kèm (BR-10.10) | `THAY_THE`, `HUONG_DAN` giữa A và B |

`structured_result = {"nguon", "dich", "tong": {"SUA_DOI": n, "BAI_BO": m}, "items": [...], "quan_he_van_ban": [...]}`; ngữ cảnh cho LLM = thống kê + 30 dòng đầu (BR-10.11), mỗi dòng là `ContextItem(chinh, nguon_truy_xuat="graph")` với nội dung "khoản 10 Điều 3 NĐ 123 – BÃI BỎ từ 01/6/2025 bởi khoản 4 Điều 2 NĐ 70".

Hướng (A sửa B hay B sửa A) xác định bằng thời gian ban hành: văn bản mới hơn là nguồn, trừ khi câu hỏi nói ngược (M09 truyền `huong` khi phát hiện "bị sửa đổi bởi").

### 3.7. API

Theo F10 §5 và F13 §5. `GET /documents/{slug}?ngay=` trả metadata + `trang_thai` tại ngày + danh sách owner kèm trạng thái (giao diện tô màu cây). `/units/lookup` mục tiêu p95 ≤ 200 ms.

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M07-T1 | Model dùng chung | `models/retrieval.py` | – | 0.25 ngày |
| M07-T2 | `effectivity/queries.py` + `service.check` | 3.2, 3.3 | 13.1–13.6 | 1 ngày |
| M07-T3 | `service.filter` + bất biến | 3.4 | 13.7–13.10 | 0.5 ngày |
| M07-T4 | DIRECT | 3.5 (stub `RelatedSearch`) | 10.1–10.3, 10.5–10.7 | 0.5 ngày |
| M07-T5 | GRAPH | 3.6 | 10.8–10.11 | 0.5 ngày |
| M07-T6 | API + đo hiệu năng | 3.7; benchmark 50 unit | – | 0.5 ngày |
| M07-T7 | Nối `RelatedSearch` BM25 | Sau khi M08 xong | 10.4 | 0.25 ngày |

## 5. Kế hoạch test

Ma trận F13 §7 trên đồ thị fixture tối thiểu dựng trong test (không phụ thuộc parser):

| Ca | Dữ liệu | Kỳ vọng |
|---|---|---|
| Còn hiệu lực | Khoản GOC `[2022-07-01, ∞)` | `con_hieu_luc` |
| Bãi bỏ | `[2022-07-01, 2025-06-01)` + `BAI_BO` | tại 2026-11-18: `het_hieu_luc`, `BAI_BO` |
| Đúng ngày `den` | d = 2025-06-01 | `het_hieu_luc` |
| Trước ngày bãi bỏ | d = 2025-03-15 | `con_hieu_luc`, `sap_thay_doi = BAI_BO` |
| Sửa đổi | 2 phiên bản | tại d sau ngày sửa: `con_hieu_luc` + `thay_doi SUA_DOI` |
| Thay thế văn bản | TT 78 + `THAY_THE` | `het_hieu_luc`, `THAY_THE` (ưu tiên hơn `BAI_BO`) |
| Chưa có hiệu lực | văn bản `hieu_luc_tu` tương lai | `chua_co_hieu_luc` |
| Hồi tố | phiên bản `tu` < ngày ban hành nguồn | tính theo `tu` |
| Thiếu ngày | `hieu_luc_tu = NULL` | `khong_xac_dinh`, không hiệu lực |
| Điểm | điểm không còn trong `diem[]` | `het_hieu_luc` |
| Phiên bản lệch | ngữ cảnh mang `@2022-07-01` của Đ19 K1 tại 2026 | bị thay bằng `@2025-06-01` |

Thêm: Q1 (hôm nay / 2025-03-15) và Q5 trên đồ thị PoC thật; benchmark 50 unit ≤ 100 ms; `/units/lookup` p95 ≤ 200 ms (100 lần gọi).

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Truy vấn `CO*` không giới hạn độ sâu chậm | Giới hạn `CO*1..4`; dùng label `:DonVi` + index |
| Logic hiệu lực bị viết lại ở nơi khác (ES range, Cypher vector) | Mọi đường truy xuất **luôn** đi qua `filter()` sau cùng (BR-08.1); lọc sớm ở ES / vector chỉ để tăng recall |
| Hướng GRAPH sai | Test cả hai chiều câu hỏi |

## 7. Bàn giao

- `EffectivityService` là phụ thuộc bắt buộc của M09, M13, M14, M15, M17.
- `RelatedSearch` có 2 hiện thực: BM25 (M08, PoC) và Local Search (M13).
