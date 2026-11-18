# Spike M00-T12 – hạ tầng (18/11/2026)

Kiểm chứng bằng test tự động trong `backend/tests/integration/` (chạy lại được bất cứ lúc nào).

| Câu hỏi | Kết quả | Test |
|---|---|---|
| GDS chạy được trên Neo4j **Community** trong Docker? | **Có.** `neo4j:5.26-community` + `NEO4J_PLUGINS=["apoc","graph-data-science"]`; `gds.version()` trả về; Leiden (`gds.leiden.stream`) trên đồ thị 2 nhóm tách biệt cho đúng 2 cụm. Projection dùng **Cypher aggregation** `gds.graph.project(...)` với `undirectedRelationshipTypes: ['*']` (Leiden yêu cầu vô hướng) | `test_neo4j_schema.py::test_plugins_available` |
| Vector index + fulltext index tạo được? | **Có.** `phienban_embedding`, `cum_embedding` (1024 chiều, cosine), `vanban_alias` (fulltext), `phienban_hieu_luc` | `test_neo4j_schema.py::test_ensure_schema_twice` |
| ICU tokenizer + `asciifolding` cho tiếng Việt? | **Có.** "Hủy hóa đơn" và "huy hoa don" → `["huy", "hoa", "don"]`; "Nghị định" → `["nghi", "dinh"]`. ICU tách theo âm tiết (đúng như dự đoán ở M08 §6) | `test_health_es.py::test_icu_folding_vietnamese` |
| Lưu ý tên index ES | Không được bắt đầu bằng `_` | – |

## Phát hiện trên máy dev Windows

| Vấn đề | Xử lý |
|---|---|
| Máy có sẵn dịch vụ **PostgreSQL 15** chiếm `0.0.0.0:5432`; Docker chỉ bind được `::` → kết nối `localhost:5432` vào nhầm PG của Windows (`password authentication failed`) | Cổng host của PG trong compose đổi thành `PG_HOST_PORT`, mặc định **5433** |
| Console Windows dùng bảng mã **cp932** → `print` / log tiếng Việt gây `UnicodeEncodeError` | `setup_logging()` và script ép stdout / stderr sang UTF-8; `scripts/dev.ps1` đặt `PYTHONUTF8=1` |
| Không có `make` | Thêm `scripts/dev.ps1` cùng tên lệnh với Makefile |
| Docker Desktop VM được cấp 8 GB | Đủ cho Neo4j (heap 1 GB) + ES (1 GB) + PG; LM Studio chạy ngoài Docker |

## Phiên bản đã dùng

Neo4j 5.26.33 Community · PostgreSQL 16.16 · Elasticsearch 8.15.3 + analysis-icu · Python 3.12 · uv 0.13.1
