# Module – Implement plan & checklist

Mỗi module trong [development-plan.md](../development-plan.md) có một thư mục riêng gồm:

| File | Dùng để |
|---|---|
| `implement-plan.md` | Thiết kế chi tiết: phạm vi, cấu trúc file, schema / migration, các bước triển khai `Mxx-Tn`, kế hoạch test, rủi ro, bàn giao |
| `checklist.md` | Danh sách việc cần tick khi làm và khi review. Mã `Mxx-Tn` khớp với bước trong implement plan |

## Danh sách

| Module | Tên | Feature | Giai đoạn | Plan | Checklist |
|---|---|---|---|---|---|
| M00 | Nền tảng & hạ tầng dev | 00-common | PoC | [plan](M00-nen-tang/implement-plan.md) | [checklist](M00-nen-tang/checklist.md) |
| M01 | LLM Gateway | F17 | PoC | [plan](M01-llm-gateway/implement-plan.md) | [checklist](M01-llm-gateway/checklist.md) |
| M02 | Thu thập & chuẩn hóa (không OCR) | F01, F02 | PoC | [plan](M02-thu-thap-chuan-hoa/implement-plan.md) | [checklist](M02-thu-thap-chuan-hoa/checklist.md) |
| M03 | Tách cấu trúc & ghi đồ thị | F03 | PoC | [plan](M03-tach-cau-truc/implement-plan.md) | [checklist](M03-tach-cau-truc/checklist.md) |
| M04 | Trích xuất quan hệ (luật mẫu) & danh mục | F04 | PoC | [plan](M04-trich-xuat-quan-he/implement-plan.md) | [checklist](M04-trich-xuat-quan-he/checklist.md) |
| M05 | Duyệt quan hệ | F05 | PoC | [plan](M05-duyet-quan-he/implement-plan.md) | [checklist](M05-duyet-quan-he/checklist.md) |
| M06 | Hợp nhất phiên bản (cơ bản) | F06 | PoC | [plan](M06-hop-nhat-phien-ban/implement-plan.md) | [checklist](M06-hop-nhat-phien-ban/checklist.md) |
| M07 | Lọc hiệu lực & tra cứu trực tiếp | F13, F10 | PoC | [plan](M07-hieu-luc-tra-cuu/implement-plan.md) | [checklist](M07-hieu-luc-tra-cuu/checklist.md) |
| M08 | Chỉ mục BM25 | F07 (BM25) | PoC | [plan](M08-chi-muc-bm25/implement-plan.md) | [checklist](M08-chi-muc-bm25/checklist.md) |
| M09 | Hỏi đáp end-to-end (không stream) | F09, F14, F08 | PoC | [plan](M09-hoi-dap-e2e/implement-plan.md) | [checklist](M09-hoi-dap-e2e/checklist.md) |
| M10 | Web chat & màn hình văn bản | UI F08, F10, F16 | PoC → MVP | [plan](M10-web-ui/implement-plan.md) | [checklist](M10-web-ui/checklist.md) |
| M11 | Mở rộng pipeline tri thức | F02 OCR, F04 LLM, F06 nâng cao | MVP | [plan](M11-mo-rong-pipeline/implement-plan.md) | [checklist](M11-mo-rong-pipeline/checklist.md) |
| M12 | Vector & phân cụm chủ đề | F07 | MVP | [plan](M12-vector-phan-cum/implement-plan.md) | [checklist](M12-vector-phan-cum/checklist.md) |
| M13 | Local Search | F11 | MVP | [plan](M13-local-search/implement-plan.md) | [checklist](M13-local-search/checklist.md) |
| M14 | Global Search | F12 | MVP | [plan](M14-global-search/implement-plan.md) | [checklist](M14-global-search/checklist.md) |
| M15 | Hỏi đáp nâng cao | F09, F14, F08 | MVP | [plan](M15-hoi-dap-nang-cao/implement-plan.md) | [checklist](M15-hoi-dap-nang-cao/checklist.md) |
| M16 | Cập nhật tăng dần & scheduler | F15 | MVP | [plan](M16-cap-nhat-tang-dan/implement-plan.md) | [checklist](M16-cap-nhat-tang-dan/checklist.md) |
| M17 | Đánh giá & phản hồi | F16 | MVP | [plan](M17-danh-gia-phan-hoi/implement-plan.md) | [checklist](M17-danh-gia-phan-hoi/checklist.md) |
| M18 | Hoàn thiện bản dev | Inception §7, §8 | MVP cuối | [plan](M18-hardening/implement-plan.md) | [checklist](M18-hardening/checklist.md) |

## Quy ước dùng chung

- **Mã bước**: `Mxx-Tn` (ví dụ `M03-T4`). Commit / PR nên ghi mã bước, ví dụ `feat(parsing): M03-T4 nhận diện khối trích dẫn`.
- **Mã quy tắc**: `BR-xx.y` tham chiếu file feature tương ứng trong [../features/](../features/). Test của một quy tắc nên đặt tên chứa mã đó, ví dụ `test_br_03_11_quoted_block_not_split`.
- **Bổ sung so với đặc tả**: mọi chỗ plan thêm bảng / cột / label / API chưa có trong file feature được đánh dấu **(bổ sung)** và cần được duyệt cùng plan.
- **Định nghĩa "Xong" chung** (áp cho mọi checklist): xem [development-plan.md §7](../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module).

## Các bổ sung so với đặc tả cần duyệt

| # | Bổ sung | Module | Lý do |
|---|---|---|---|
| 1 | Bảng `api_key` (hash key, vai trò) | M00 | 00-common §6 nêu `X-API-Key` gắn vai trò nhưng chưa có nơi lưu |
| 2 | Cột `priority`, `run_after`, `dedupe_key` trong `pipeline_job`; tạo bảng `pipeline_run`/`pipeline_job` ngay từ M00 | M00 | Hàng đợi dùng chung cho mọi module từ PoC; chống tạo job trùng (F15 §7) |
| 3 | Đồng hồ hệ thống thay được (`APP_FAKE_TODAY`) | M00 | F15 §7 cần giả lập ngày 01/01/2026 |
| 4 | Bảng `runtime_flag` cho cờ `interactive_busy` dùng chung giữa process API và worker | M01 | BR-17.7 – semaphore trong bộ nhớ không thấy được process khác |
| 5 | Bảng `source_document_event` (lịch sử trạng thái) | M02 | F01 API "chi tiết + lịch sử trạng thái" chưa có bảng |
| 6 | Label phụ `:DonVi` + constraint `donvi_id` cho mọi Chương / Điều / Khoản / Điểm | M03 | Các truy vấn `MATCH (u {id: …})` không label ở F06, F13 sẽ quét toàn đồ thị |
| 7 | Bảng `index_outbox` (phiên bản tạo / sửa / xóa chờ đồng bộ ES) | M06 | F07 BR-07.5 cần biết phiên bản bị xóa sau hợp nhất |
| 8 | Khung frontend tạo ngay ở M05 (trang duyệt) | M05 | Chuyên gia cần giao diện duyệt trước khi có web chat |
| 9 | Cột `relation_candidate.nguon_hieu_luc_tu` (tùy chọn) | M05 | Sắp hàng đợi duyệt theo BR-05.2 không cần truy vấn Neo4j |
| 10 | Thêm sớm cột `source_document.indexed_at` (F15 §6) | M08 | Cần ngay khi văn bản chuyển `INDEXED` |
| 11 | Thuộc tính `PhienBan.embedding_model` | M12 | Phát hiện đổi model embedding (BR-07.4) |
| 12 | Trường `ContextItem.unit_ids` | M14 | Một ý tổng hợp của Global Search có nhiều điều khoản nguồn; verifier cần biết |
| 13 | Bảng `notification` + API `POST /ingest/source-documents/{id}/confirm-revision` | M16 | Thông báo biên tập viên / quản trị; xác nhận bản đính chính (BR-15.5) |

| 14 | Model thực tế: DeepSeek R1 0528 Qwen3 8B + nomic-embed-text v1.5 (768 chiều) thay Qwen3.5 9B + bge-m3 | M01, M09, M12, M13, M15 | Quyết định 19/11/2026 – xem [spike](../spikes/lmstudio.md); mỗi plan bị ảnh hưởng có khối "Ảnh hưởng của model thực tế" |

> Số thứ tự migration ghi trong các plan (`0001_base`, `0002_llm`…) chỉ để minh họa thứ tự; khi làm dùng revision Alembic tự sinh.
