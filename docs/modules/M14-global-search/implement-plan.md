# M14 – Global Search · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F12 – Global Search](../../features/F12-global-search.md) |
| Giai đoạn | MVP – tuần 8–9 |
| Ước lượng | 4 ngày |
| Phụ thuộc | M12 (cụm, tóm tắt, `cum_embedding`), M07 (`EffectivityService`), M11 (chủ đề / đối tượng), M01 (`global_map`) |
| Module dùng kết quả | M15 (route `GLOBAL`), M10 (trang chủ đề) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Trả lời câu hỏi tổng hợp (Q3) bằng hai nguồn: **(1) danh sách xác định từ đồ thị** (Điều theo chủ đề + đối tượng, còn hiệu lực tại ngày) và **(2) map-reduce trên ≤ 3 cụm** để có ý chính có nguồn. Hoàn thành ≤ 20 s hoặc trả `partial = true`.

## 2. Thiết kế

### 2.1. Cấu trúc file

```text
backend/app/retrieval/global_/
├── config.py        # GLOBAL_* (F12 §6.3)
├── graph_filter.py  # Cypher F12 §6.1 (BR-12.1, 12.2)
├── select.py        # chọn ≤ 3 cụm (BR-12.3)
├── map_step.py      # map một cụm → MapOutput (BR-12.4, 12.5)
├── reduce_step.py   # gộp, khử trùng, top 15 → ContextItem tong_hop (BR-12.6)
├── recent.py        # notice văn bản cùng chủ đề hết hiệu lực trong 12 tháng (BR-12.9)
├── searcher.py      # GlobalSearcher.search(analysis, on_progress) → RetrievalResult
└── router.py        # POST /search/global, GET /topics/{ma_chu_de}/documents
```

### 2.2. Luồng

```python
async def search(a: QueryAnalysis, on_progress=lambda i, n: None) -> RetrievalResult:
    deadline = now() + GLOBAL_TIMEOUT_S
    listing = await graph_filter(a.chu_de, a.doi_tuong, a.ngay_ap_dung) if (a.chu_de or a.doi_tuong) else None
    clusters = await select_clusters(a.cau_hoi_doc_lap, listing, max=GLOBAL_MAX_CLUSTERS)
    if not listing and not clusters: return RetrievalResult(contexts=[])     # UC-12.1 ngoại lệ 1a
    points, partial = [], False
    for i, c in enumerate(clusters, 1):
        if now() >= deadline: partial = True; break                         # BR-12.8
        on_progress(i, len(clusters))                                       # sự kiện SSE progress
        points += await map_cluster(a, c, ngay=a.ngay_ap_dung, timeout=min(15, deadline - now()))
    ctx = reduce(points, max=GLOBAL_MAX_POINTS)
    notices = await recently_expired(a.chu_de, a.ngay_ap_dung, months=12)
    r = RetrievalResult(contexts=ctx, notices=notices,
                        structured_result={"van_ban": listing_rows(listing)} if listing else None)
    r = effectivity.filter(r, a.ngay_ap_dung)
    r.partial = partial
    return r
```

### 2.3. Chi tiết quy tắc

| Quy tắc | Cách làm |
|---|---|
| Lọc đồ thị (BR-12.1) | Cypher F12 §6.1 – xác định, không dùng LLM; mỗi văn bản kèm `trang_thai` tại ngày (F13) và danh sách Điều; đây là nguồn chính cho câu "gồm những văn bản nào" |
| Không có chủ đề / đối tượng (BR-12.2) | Bỏ lọc đồ thị, chỉ map-reduce |
| Chọn cụm (BR-12.3) | `queryNodes('cum_embedding', 5, qvec)` ∪ cụm chứa Điều ở BR-12.1; xếp theo số Điều khớp (rồi theo độ tương đồng); cụm tương đồng < 0.5 và không chứa Điều khớp → loại; lấy ≤ 3 |
| Map (BR-12.4) | Đầu vào: tóm tắt cụm (chỉ để định hướng) + Điều trong cụm **còn hiệu lực tại `ngay_ap_dung`** – label + nội dung phiên bản tại ngày rút gọn, ≤ 2 500 token; `complete_json("global_map", …, MapOutput)` |
| Chống bịa (BR-12.5) | `unit_ids` của ý phải thuộc tập Điều / Khoản đã đưa vào map; không → bỏ ý. `diem < 30` → bỏ |
| Reduce (BR-12.6) | Gộp ý của các cụm, khử trùng theo tập `unit_ids` (Jaccard ≥ 0.8 → giữ ý điểm cao), sắp theo điểm, top 15 → `ContextItem(vai_tro = tong_hop, nguon_truy_xuat = "global", noi_dung = "Ý: …", unit_id = unit_ids[0], score = diem)`; giữ toàn bộ `unit_ids` trong trường phụ để F14 dẫn nguồn |
| Ngày quá khứ (BR-12.7) | `ngay_ap_dung ≠ hôm nay` → **không** đưa `tom_tat` vào prompt map (tóm tắt tạo theo hôm nay); chỉ dùng tóm tắt để chọn cụm |
| Thời gian (BR-12.8) | Hạn 20 s; cụm chưa map bị bỏ; `partial = true` |
| Notice (BR-12.9) | Văn bản có `THUOC_CHU_DE ∈ chu_de`, `hieu_luc_den ∈ (d − 12 tháng, d]` → `Notice` (vd TT 78/2021) |

### 2.4. Tích hợp

- `qa/chat/pipeline.retrieve`: route `GLOBAL` → `GlobalSearcher.search(a, on_progress=sse_progress)`; bỏ "BM25 tạm".
- Ngân sách thời gian chat cho `GLOBAL`: 20 s truy xuất (BR-08.4) – pipeline không áp timeout 1.5 s cho route này.
- `ContextItem` cần thêm trường tùy chọn `unit_ids: list[str] = []` **(bổ sung cho F10 §6.2)** để verifier (M15) chấp nhận trích dẫn tới mọi điều khoản nguồn của một ý tổng hợp.
- `GET /topics/{ma_chu_de}/documents?doi_tuong=&ngay=` trả kết quả BR-12.1 cho trang chủ đề (M10).

## 3. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M14-T1 | `graph_filter.py` + API `/topics/{ma_chu_de}/documents` | 2.3 | 12.1, 12.2 | 0.5 ngày |
| M14-T2 | `select.py` | 2.3 | 12.3 | 0.5 ngày |
| M14-T3 | `map_step.py` + prompt + chống bịa | 2.3 | 12.4, 12.5, 12.7 | 1 ngày |
| M14-T4 | `reduce_step.py` | 2.3 | 12.6 | 0.5 ngày |
| M14-T5 | `recent.py` + `searcher.py` (deadline, progress) + `/search/global` | 2.2 | 12.8, 12.9 | 0.75 ngày |
| M14-T6 | Tích hợp pipeline + golden Q3 | 2.4 | – | 0.75 ngày |

## 4. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Tích hợp | Q3 → `structured_result.van_ban` chứa NĐ 123 (đã sửa), NĐ 70/2025, TT 32/2025; **không** chứa TT 78/2021; TT 78 nằm trong `notices` |
| Unit (mock LLM) | Map trả ý có `unit_id` ngoài đầu vào → bị bỏ; ý điểm 20 → bị bỏ |
| Unit | Reduce: 2 ý trùng `unit_ids` từ 2 cụm → giữ 1 |
| Tích hợp (mock LLM chậm 10 s / cụm) | Trả sau ≤ 20 s với `partial = true`, có kết quả cụm đầu + danh sách đồ thị |
| Tích hợp | Ngày 2025-03-15 → prompt map không chứa `tom_tat`; ngữ cảnh chỉ gồm phiên bản hiệu lực tại ngày đó |
| Bất biến | Mọi `unit_ids` trong ngữ cảnh tổng hợp tồn tại và còn hiệu lực tại ngày áp dụng |

## 5. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| 3 lời gọi map tuần tự trên LLM local vượt 20 s | Map tắt thinking, ≤ 2 500 token đầu vào; `partial`; giảm `GLOBAL_MAX_CLUSTERS` xuống 2 nếu đo thấy chậm |
| Cụm Leiden không khớp chủ đề | Danh sách đồ thị (BR-12.1) không phụ thuộc cụm – vẫn đúng phần "gồm những văn bản nào" |
| Ý tổng hợp diễn đạt sai nội dung điều khoản | F14 sinh câu trả lời cuối từ ý + nguồn; verifier kiểm trích dẫn; M17 đo |

## 6. Bàn giao

- M15 phát sự kiện SSE `progress` từ callback `on_progress`.
- Trường `ContextItem.unit_ids` được verifier M15 sử dụng.
