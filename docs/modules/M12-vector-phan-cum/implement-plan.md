# M12 – Vector & phân cụm chủ đề · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F07 – Lập chỉ mục & tóm tắt cụm](../../features/F07-lap-chi-muc.md) – BR-07.1 → 07.4, BR-07.8 → 07.13 |
| Giai đoạn | MVP – tuần 7 |
| Ước lượng | 4–5 ngày |
| Phụ thuộc | M08 (runner `index`, outbox), M11 (cạnh chủ đề / đối tượng), M01 (`embed`, `summarize_cluster`) |
| Module dùng kết quả | M13 (vector), M14 (cụm + tóm tắt), M16 (phân cụm lại hằng tuần) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

- Embedding bge-m3 (1024 chiều) cho mọi `PhienBan`, cập nhật tăng dần theo `embedding_stale`.
- Phân cụm Leiden (Neo4j GDS) trên đồ thị Điều – chủ đề – đối tượng, tóm tắt mỗi cụm bằng Qwen, embedding tóm tắt cho Global Search.
- Văn bản chỉ `INDEXED` khi đủ BM25 **và** embedding.

## 2. Thiết kế

### 2.1. Cấu trúc file

```text
backend/app/indexing/
├── embed_text.py      # build_embedding_text(pb, owner, dieu, van_ban) – BR-07.2
├── embed_sync.py      # PhienBan stale → embed lô 32 → SET embedding (BR-07.1, 07.3)
├── model_change.py    # đổi EMBEDDING_MODEL / DIM → đánh dấu toàn bộ stale, tạo lại vector index (BR-07.4)
├── communities/
│   ├── project.py     # chiếu đồ thị GDS (BR-07.8)
│   ├── leiden.py      # chạy Leiden, ghi Cum / THUOC_CUM / CUM_CHA, gộp cụm nhỏ (BR-07.9)
│   ├── assign.py      # tăng dần: gán Điều mới vào cụm láng giềng, đánh dấu dirty (BR-07.12)
│   ├── summarize.py   # tóm tắt cụm dirty + embedding tóm tắt (BR-07.10, 07.11, 07.13)
│   └── models.py      # ClusterSummary (F07 §6.4)
└── topics_router.py   # GET /topics, GET /topics/{cum_id}
```

### 2.2. Embedding

| Quy tắc | Cách làm |
|---|---|
| Văn bản đầu vào (BR-07.2) | `"{loai} {so_hieu} – {trich_yeu}\nĐiều {so}. {tieu_de_dieu}\nKhoản {so}: {noi_dung}"` (Điều không khoản bỏ dòng Khoản) |
| Lô (BR-07.3) | 32 văn bản / lời gọi, `priority = 3`, `wait_if_interactive_busy()` giữa các lô |
| Văn bản dài | > `EMBED_MAX_TOKENS` (mặc định 8 000 theo ước lượng M01) → cắt theo ranh giới điểm / câu, embedding = trung bình các đoạn, chuẩn hóa L2 |
| Ghi | `UNWIND $rows SET pb.embedding = r.vec, pb.embedding_stale = false, pb.embedding_model = $model` – lưu thêm `embedding_model` để phát hiện đổi model |
| Nguồn stale | `PhienBan.embedding_stale = true` (M03, M06 đặt) – không cần outbox |
| Lỗi LM Studio | Giữ stale, job retry; văn bản chưa `INDEXED` (UC-07.1 ngoại lệ 2a) |
| Đổi model (BR-07.4) | Khi khởi động: `EMBEDDING_MODEL` khác model trên phần lớn phiên bản → cảnh báo; API `POST /index/runs {"mode":"full","parts":["embedding"]}` đánh dấu toàn bộ stale; số chiều khác → `DROP` + `CREATE VECTOR INDEX` mới |

Truy vấn embedding câu hỏi (M13, M14) dùng `priority = 1`.

### 2.3. Phân cụm Leiden

| Bước | Cách làm |
|---|---|
| Chiếu (BR-07.8) | Dùng **Cypher projection dạng aggregation** (`gds.graph.project` trong `MATCH … RETURN gds.graph.project(…)`) thay cho `gds.graph.project.cypher` (đã deprecated ở GDS 2.x). Node: `Dieu`, `ChuDe`, `DoiTuong`. Cạnh: `THUOC_CHU_DE`, `AP_DUNG_CHO`, `VIEN_DAN` (quy về Điều), `HUONG_DAN` (cạnh cấp văn bản được quy về Điều: chỉ nối các Điều của Thông tư với các Điều của văn bản đích **có chung ít nhất một chủ đề**, để tránh bùng nổ số cạnh), `SUA_DOI` quy về Điều (trọng số 2). Khai báo vô hướng (`undirectedRelationshipTypes: ['*']`) |
| Chạy (BR-07.9) | `gds.leiden.write` với `includeIntermediateCommunities: true`, `maxLevels: 2`, `randomSeed: 42`, `relationshipWeightProperty: 'weight'`. Ghi `communityId` cấp thấp + `intermediateCommunityIds` |
| Ghi cụm | Mỗi cộng đồng → `Cum {id: "cum-<cap>-<n>", cap}`; `(Dieu)-[:THUOC_CUM]->(Cum cấp thấp)`, `(Cum thấp)-[:CUM_CHA]->(Cum cao)`; `Dieu.cum_id`. Node `ChuDe` / `DoiTuong` chỉ để kéo các Điều lại gần, không gán vào cụm |
| Cụm nhỏ | Cụm < 3 Điều → gộp vào cụm láng giềng có nhiều cạnh nhất (tính trên đồ thị chiếu) |
| Ổn định ID | Lần phân cụm mới: khớp cụm mới với cụm cũ theo Jaccard tập Điều ≥ 0.5 → giữ `id` cũ (để link `/topics/{cum_id}` ổn định); cụm không khớp → ID mới; cụm cũ không còn → xóa |
| Sau phân cụm | Mọi cụm `dirty = true` → tóm tắt lại (UC-07.2); drop graph projection |

### 2.4. Tăng dần (BR-07.12)

- Điều mới (chưa có `THUOC_CUM`): gán vào cụm của láng giềng (qua các cạnh chiếu ở 2.3) xuất hiện nhiều nhất; không có láng giềng → cụm theo chủ đề đầu tiên của Điều; vẫn không có → để trống tới lần phân cụm lại.
- Outbox `upsert` / `delete` (M06) của phiên bản thuộc Điều trong cụm → `Cum.dirty = true`.
- Leiden toàn bộ chạy hằng tuần (M16) hoặc thủ công (`parts: ["communities"], mode: "full"`).

### 2.5. Tóm tắt cụm

- Đầu vào: Điều trong cụm **còn hiệu lực hôm nay** (dùng `EffectivityService.check`) – label + nội dung rút gọn ≤ 300 ký tự / Điều, tổng ≤ 6 000 token (ưu tiên Điều có nhiều cạnh).
- `complete_json("summarize_cluster", …, ClusterSummary)`; hậu kiểm: `van_ban_chinh` chỉ giữ số hiệu có trong đồ thị (F07 §7), `chu_de` / `doi_tuong` chỉ giữ mã trong danh mục.
- `SET c.tieu_de, c.tom_tat, c.van_ban_chinh, c.doi_tuong, c.chu_de, c.ngay_tom_tat = today, c.dirty = false`; embedding `tom_tat` → `c.tom_tat_embedding` (BR-07.13).
- Tóm tắt **chỉ** dùng để chọn cụm (BR-07.11); ghi chú này vào docstring để M14 không dùng sai.

### 2.6. Runner và trạng thái

- Runner `index` (M08) điều phối `parts`: `bm25` → `embedding` → `communities` (incremental: assign + summarize dirty; full: Leiden + summarize tất cả).
- Điều kiện `INDEXED`: đủ doc ES **và** không còn phiên bản stale của văn bản.
- `/index/status` thêm `phien_ban_stale`, `clusters`, `clusters_dirty`, `embedding_model`, `last_full_clustering` (F07 §5).

### 2.7. API

`GET /topics` (danh sách cụm cấp cao + cấp thấp: tiêu đề, tóm tắt, văn bản chính, số Điều), `GET /topics/{cum_id}` (chi tiết + Điều thuộc cụm kèm trạng thái hôm nay).

## 3. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M12-T1 | Embedding text + sync + stale | 2.2 | 07.1–07.3 | 1 ngày |
| M12-T2 | Đổi model | 2.2 | 07.4 | 0.25 ngày |
| M12-T3 | Chiếu GDS + Leiden + ghi cụm + gộp cụm nhỏ + ổn định ID | 2.3 | 07.8, 07.9 | 1.5 ngày |
| M12-T4 | Tăng dần: assign + dirty | 2.4 | 07.12 | 0.5 ngày |
| M12-T5 | Tóm tắt + embedding tóm tắt | 2.5 | 07.10, 07.11, 07.13 | 0.75 ngày |
| M12-T6 | Runner, `INDEXED`, `/index/status`, `/topics` | 2.6, 2.7 | – | 0.5 ngày |

## 4. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit | `build_embedding_text` cho Khoản và Điều không khoản; cắt văn bản dài + trung bình |
| Tích hợp (mock embed) | Sau index: `phien_ban_stale = 0`; sửa 1 khoản → chỉ phiên bản mới được embed |
| Tích hợp | Vector index trả kết quả với `db.index.vector.queryNodes('phienban_embedding', …)` |
| Tích hợp GDS | Đồ thị fixture nhỏ (2 nhóm Điều tách biệt) → Leiden ra 2 cụm; chạy lại với cùng seed → cùng kết quả, ID cụm giữ nguyên |
| Tích hợp | Cụm 2 Điều → bị gộp |
| Tích hợp (mock LLM) | Tóm tắt có `van_ban_chinh` bịa → bị lọc |
| Tích hợp | Sửa 1 khoản → chỉ cụm chứa Điều đó `dirty` và được tóm tắt lại |
| Thủ công | Đọc tóm tắt các cụm trên dữ liệu thật – có ý nghĩa với chủ đề hóa đơn điện tử / thuế hộ kinh doanh |

## 5. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Đồ thị nhỏ (vài trăm Điều) → Leiden cho cụm lớn / vô nghĩa | Điều chỉnh `gamma` (resolution); kiểm tra thủ công; cụm theo `ChuDe` làm phương án dự phòng cho M14 |
| GDS Community giới hạn tính năng | Đã spike ở M00-T12; Leiden có trong bản Community |
| Thời gian tóm tắt (LLM local) | Chỉ cụm dirty; chạy ngoài giờ; nhường chat |
| Bùng nổ cạnh khi quy `HUONG_DAN` cấp văn bản về Điều | Quy tắc nối có điều kiện chủ đề chung (2.3); đo số cạnh chiếu |

## 6. Bàn giao

- M13 dùng `phienban_embedding` + `embed(…, priority=1)`.
- M14 dùng `cum_embedding`, `THUOC_CUM`, `Cum.tom_tat` (chỉ để chọn cụm).
- M16 đặt lịch `weekly_recluster` gọi `index {"mode":"full","parts":["communities"]}`.
