# M13 – Local Search · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F11 – Local Search](../../features/F11-local-search.md) |
| Giai đoạn | MVP – tuần 8 |
| Ước lượng | 4 ngày |
| Phụ thuộc | M12 (vector), M08 (`bm25_search`), M07 (`EffectivityService`) |
| Module dùng kết quả | M15 (route `LOCAL`), M07 (`RelatedSearch` cho BR-10.4), M10 (trang tìm kiếm) |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Tìm điều khoản cho **câu hỏi tình huống** (Q2, Q4): vector + BM25 có lọc hiệu lực ngay khi truy xuất, hợp nhất RRF, thu thập notice từ các đoạn "giống nhưng đã hết hiệu lực", mở rộng đồ thị 1 bước, cắt theo ngân sách ~3 000 token. Thay nhánh "BM25 tạm" của M09.

## 2. Thiết kế

### 2.1. Cấu trúc file

```text
backend/app/retrieval/local/
├── config.py       # LOCAL_* (F11 §6.3)
├── vector.py       # vector_search(qvec, ngay, so_hieu, k) – Cypher F11 §6.1
├── notices.py      # vector top 10 không lọc → ứng viên notice (BR-11.6)
├── fuse.py         # RRF + boost chủ đề / đối tượng (BR-11.4, 11.5)
├── expand.py       # mở rộng 1 bước (bảng F11 §1.2)
├── budget.py       # cắt ngân sách token, cắt nội dung tại ranh giới điểm (BR-11.9)
├── searcher.py     # LocalSearcher.search(...) → RetrievalResult
└── router.py       # POST /search/local
```

### 2.2. Luồng

```python
async def search(q: str, ngay: date, filters: Filters, tu_khoa: list[str], top_k=12, expand=True):
    try:   qvec = await gw.embed([q], priority=1)
    except LLMError: qvec = None; degraded = True                  # UC-11.1 ngoại lệ 1a
    vec, bm, raw = await gather(
        vector_search(qvec, ngay, filters.so_hieu, k=LOCAL_VECTOR_K) if qvec else [],
        bm25_search(q, ngay, so_hieu=filters.so_hieu, tu_khoa=tu_khoa,
                    chu_de=filters.chu_de, doi_tuong=filters.doi_tuong, k=LOCAL_BM25_K),  # ES lỗi → []
        vector_unfiltered(qvec, k=10) if qvec else [],
    )
    seeds = rrf(vec, bm, k=LOCAL_RRF_K) + boost(chu_de, doi_tuong, +0.1)[:LOCAL_SEEDS]
    notices = to_notices([h for h in raw if h not in active_set and h.rank < 10])[:LOCAL_MAX_NOTICES]
    ctx = [ContextItem(chinh, nguon_truy_xuat=h.source) for h in seeds]
    if expand: ctx += await expand_one_hop(seeds, ngay, filters.doi_tuong)   # điểm = 0.5 × hạt giống
    result = effectivity.filter(RetrievalResult(contexts=dedupe(ctx), notices=notices), ngay)  # BR-11.7
    return budget.cut(result, LOCAL_CONTEXT_TOKENS)
```

### 2.3. Chi tiết quy tắc

| Quy tắc | Cách làm |
|---|---|
| Vector (BR-11.2) | `queryNodes('phienban_embedding', 90, $qvec)` rồi lọc hiệu lực phiên bản + văn bản, giới hạn `so_hieu` nếu có, `LIMIT 30` |
| BM25 (BR-11.3) | `bm25_search` (M08) – đã lọc range + tìm cả `noi_dung.folded` |
| Boost (BR-11.4) | +0.1 vào điểm RRF nếu Điều cha có `THUOC_CHU_DE ∈ chu_de` / `AP_DUNG_CHO ∈ doi_tuong`; **không** lọc cứng |
| RRF (BR-11.5) | `score = Σ 1/(60 + rank)` theo `unit_id` (không theo `phien_ban_id`, vì hai nhánh có thể trả phiên bản khác nhau của cùng điều khoản – giữ phiên bản hiệu lực tại ngày) |
| Notice (BR-11.6) | Kết quả vector **không lọc** top 10 mà không có hiệu lực tại `d` → `EffectivityService.check` để có `ThayDoi` → `Notice` (≤ 3) |
| Mở rộng (F11 §1.2) | Tiêu đề Điều cha (luôn, đưa vào label); Khoản anh em khi hạt giống < 200 ký tự (`phu`); `VIEN_DAN` đi ra từ Điều hạt giống (`phu`); Thông tư `HUONG_DAN` đi vào (`phu`); `SUA_DOI` đi vào → `nguon_sua_doi`; tối đa 20 node |
| Điểm mở rộng (BR-11.8) | 0.5 × điểm hạt giống nguồn; khử trùng theo `unit_id`, giữ điểm cao nhất |
| Ngân sách (BR-11.9) | Sắp theo điểm; cộng `estimate_tokens(noi_dung)`; vượt → cắt nội dung khoản dài tại ranh giới điểm `a) b) …`; tối đa ~12 ngữ cảnh |
| Rỗng (BR-11.10) | Không ngữ cảnh → trả rỗng kèm notices để F14 nói "không tìm thấy quy định đang có hiệu lực, nhưng có quy định đã hết hiệu lực…" |

Mọi truy vấn Neo4j của mở rộng gom thành **một** truy vấn `UNWIND $seed_unit_ids` để đạt p95 ≤ 1.5 s.

### 2.4. Tích hợp

- `qa/chat/pipeline.retrieve`: route `LOCAL` → `LocalSearcher.search(a.cau_hoi_doc_lap, a.ngay_ap_dung, Filters(so_hieu=a.van_ban, chu_de=a.chu_de, doi_tuong=a.doi_tuong), a.tu_khoa)`; bỏ nhánh "BM25 tạm".
- `retrieval/direct/related.py`: hiện thực `RelatedSearch` mới gọi `LocalSearcher.search(noi_dung_cu, ngay, Filters(so_hieu=liên quan), expand=False, top_k=3)` (BR-10.4).
- `debug` trong response: `vector_hits`, `bm25_hits`, `filtered_out`, `expanded`, `tokens`, `degraded` (F11 §5).

## 3. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M13-T1 | `vector.py` + `notices.py` | 2.3 | 11.2, 11.6 | 0.5 ngày |
| M13-T2 | `fuse.py` | RRF + boost | 11.4, 11.5 | 0.5 ngày |
| M13-T3 | `expand.py` | 1 truy vấn `UNWIND` | 11.7, 11.8 | 1 ngày |
| M13-T4 | `budget.py` | Cắt tại ranh giới điểm | 11.9, 11.10 | 0.5 ngày |
| M13-T5 | `searcher.py` + degraded + API | 2.2 | 11.1, 11.3 | 0.5 ngày |
| M13-T6 | Tích hợp pipeline + `RelatedSearch` + đo hiệu năng | 2.4 | 10.4 | 0.5 ngày |
| M13-T7 | Golden Q2, Q4 | Thêm vào `tests/e2e/golden.yaml` | – | 0.5 ngày |

## 4. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit `fuse` | Hai danh sách có giao → điểm RRF đúng; boost +0.1 không đẩy kết quả không liên quan lên đầu |
| Unit `budget` | Khoản dài bị cắt tại `b)`; không vượt ngân sách |
| Tích hợp | Q2 → ngữ cảnh có quy định hiện hành về HĐĐT khởi tạo từ máy tính tiền cho hộ kinh doanh (NĐ 123 sửa đổi bởi NĐ 70) |
| Tích hợp | Q4 (`2025-03-15`) → mọi ngữ cảnh `hieu_luc_tu <= 2025-03-15 < hieu_luc_den`; có nội dung TT 78/2021, không có TT 32/2025 |
| Tích hợp | Câu hỏi khớp mạnh với khoản đã bãi bỏ → khoản đó nằm trong `notices`, không nằm trong `contexts` |
| Tích hợp | Embedding lỗi → `degraded = true`, vẫn có kết quả BM25; ES lỗi → chỉ vector |
| Bất biến | `assert_invariant()` trên mọi kết quả |
| Hiệu năng | 50 câu hỏi đánh giá route `LOCAL` → p95 ≤ 1.5 s (không tính embedding nếu LM Studio bận – ghi riêng) |

## 5. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Embedding câu hỏi chậm khi LM Studio đang sinh câu trả lời khác | Semaphore embedding riêng (M01); `priority = 1` |
| Lọc hiệu lực sau vector làm mất kết quả (k = 90 vẫn thiếu) | Theo dõi `filtered_out`; tăng hệ số lấy dư nếu < 10 kết quả còn lại |
| Hạt giống toàn khoản ngắn ("Bãi bỏ…") | Văn bản embedding có tiêu đề ngữ cảnh (M12); mở rộng Khoản anh em |

## 6. Bàn giao

- M15 dùng `LocalSearcher` cho route `LOCAL` và cho fallback `DIRECT`/`GRAPH` rỗng.
- M10 trang `/tim-kiem` gọi `POST /search/local`.
