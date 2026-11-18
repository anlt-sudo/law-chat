# M11 – Mở rộng pipeline tri thức · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F02](../../features/F02-chuan-hoa-ocr.md) (OCR), [F04](../../features/F04-trich-xuat-quan-he.md) (tầng LLM + phân loại), [F06](../../features/F06-hop-nhat-phien-ban.md) (cấp Điểm, `BO_SUNG`) |
| Giai đoạn | MVP – tuần 5–6 |
| Ước lượng | 6–8 ngày |
| Phụ thuộc | M01–M06 (đã có ở PoC) |
| Module dùng kết quả | M12, M13, M14, M17 |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Hoàn thiện ba bước của Epic A mà PoC còn thiếu, và mở rộng dữ liệu sang mảng **thuế hộ kinh doanh** (inception §10):

1. **OCR** cho PDF scan / ảnh (F02 BR-02.1, 02.2, 02.8).
2. **Tầng LLM** của trích xuất quan hệ cho câu khó + **phân loại chủ đề / đối tượng** bằng LLM (F04 BR-04.2, 04.3, 04.15).
3. **Hợp nhất cấp Điểm, `BO_SUNG` Khoản / Điều / Điểm** (F06 §1.2 phần còn lại, BR-06.9).

## 2. Phạm vi

| Phần | Trong M11 |
|---|---|
| OCR | PaddleOCR tiếng Việt (mặc định) + Tesseract `vie` (dự phòng); điểm tin cậy theo trang; `NEEDS_ATTENTION` khi < 0.85 |
| F04 LLM | Câu có trigger mà luật không khớp đủ → `extract_relations`; kết quả LLM → `legal/refs` chuyển sang ID (LLM **không** sinh ID); conf = min(tự đánh giá, 0.8); JSON lỗi 3 lần → `manual_required` |
| F04 phân loại | Điều không khớp từ khóa → `classify_topics` chọn trong danh mục |
| F06 | `SUA_DOI` Điểm, `BO_SUNG` Điểm / Khoản / Điều, `BAI_BO` Điểm, Điều bổ sung (`Đ9a`), `DIEM_NOT_FOUND` |
| Dữ liệu | Thêm 10–20 văn bản thuế hộ kinh doanh qua M02 → M08; chạy lại toàn pipeline |

## 3. Thiết kế

### 3.1. OCR

```text
backend/app/ingest/normalize/ocr/
├── base.py        # OcrEngine Protocol: recognize(image) → list[OcrLine(text, conf, bbox)]
├── paddle.py      # PaddleOCR(lang="vi")
├── tesseract.py   # pytesseract, lang="vie"
└── render.py      # PyMuPDF render trang → ảnh 300 DPI
```

| Quyết định | Chi tiết |
|---|---|
| Đóng gói | Phụ thuộc OCR nặng (PaddlePaddle) → extra `uv` riêng `ocr` + image worker riêng `worker-ocr` trong compose, chỉ nhận job `normalize` có trang scan (`payload.needs_ocr = true`). Image backend chính không cần cài |
| Lựa chọn engine | Paddle trước; lỗi / conf trung bình < 0.6 → thử Tesseract, lấy kết quả conf cao hơn |
| Gộp vào luồng F02 | Dòng OCR thành block (`is_ocr = true`, `conf`) rồi đi qua đúng các bước chuẩn hóa hiện có |
| Kiểm tra chéo (rủi ro inception §8) | Số hiệu đọc từ OCR phải khớp metadata nguồn; số Điều liên tục (M03 BR-03.14) – vi phạm nhiều → `NEEDS_ATTENTION` |
| Xác định (BR-02.9) | Ghim phiên bản model OCR trong `normalizer_version` |

### 3.2. Tầng LLM của F04

```python
class RelationLLMOut(BaseModel): ...      # F04 §6.2
class RelationLLMResponse(BaseModel): quan_he: list[RelationLLMOut]

prompt = system(
  "Bạn trích xuất quan hệ giữa các văn bản pháp luật. Chỉ trả JSON đúng schema. "
  "Không tự tạo số hiệu không có trong câu hoặc ngữ cảnh."
) + user(câu, tiêu đề Điều chứa câu, văn bản đích mặc định, văn bản hiện tại)
```

- Batch: gom ≤ 5 câu / lời gọi nếu context cho phép (giảm số lần gọi); gọi `wait_if_interactive_busy()` trước mỗi lô (BR-17.7).
- Kiểm hậu xử lý: `van_ban_dich` phải xuất hiện trong câu hoặc ngữ cảnh, nếu không → bỏ, cảnh báo `LLM_HALLUCINATED_DOC`.
- LM Studio không phản hồi → job `extract` hoãn 10 phút (`run_after`), ứng viên tầng 1 vẫn lưu (F04 ngoại lệ 4a).
- Ghi `llm_call_id` vào ứng viên.

### 3.3. Phân loại chủ đề / đối tượng

- Đầu vào: tiêu đề + 600 ký tự đầu của Điều + danh mục (mã + tên + mô tả ngắn).
- Output `{chu_de: list[ma], doi_tuong: list[ma]}`; mã ngoài danh mục → bỏ (BR-04.14).
- Cạnh `THUOC_CHU_DE` / `AP_DUNG_CHO` `{nguon: 'llm'}`; cạnh `nguon: 'bien_tap'` không bị ghi đè khi chạy lại.

### 3.4. Hợp nhất cấp Điểm và `BO_SUNG`

Mở rộng `apply.py` và `rebuild.py` của M06:

| Sự kiện | Cách áp |
|---|---|
| `SUA_DOI` Điểm `x` của Khoản `K` | Tách nội dung phiên bản hiện tại của `K` thành câu dẫn + danh sách điểm (dùng `parsing/structure.py`); thay đoạn điểm `x` bằng `noi_dung_moi`; ghép lại; phiên bản mới của `K` |
| `BO_SUNG` Điểm `x` | Chèn điểm theo thứ tự chữ cái (`a, b, c, d, đ, e…`; `d1`, `đ1` sau `d`, `đ`); cập nhật `diem[]`; tạo node `Diem` mới (`MERGE`) + `CO` từ `K` |
| `BAI_BO` Điểm `x` | Xóa đoạn điểm, cập nhật `diem[]`, phiên bản mới của `K`; node `Diem` giữ lại (cho truy vấn lịch sử) |
| `BO_SUNG` Khoản / Điều | Tạo node mới + `CO` từ cha (`thu_tu` theo số), phiên bản đầu tiên `hieu_luc_tu = d`, `loai_thay_doi = BO_SUNG`; cạnh `SUA_DOI {kieu: BO_SUNG}` từ nguồn được tạo **sau** khi có node đích |
| Không tìm thấy điểm | `DIEM_NOT_FOUND`, không tạo phiên bản (BR-06.9) |
| `SUA_DOI` cả Điều có nhiều khoản | Thay thế cách xử lý tạm của M06 bằng tách `noi_dung_moi` thành Khoản: khoản có trong cả hai → sửa; khoản mới → `BO_SUNG`; khoản cũ không còn → đóng (bãi bỏ ngầm) + cảnh báo để biên tập viên xác nhận |

Ứng viên `BO_SUNG` đã duyệt ở PoC (cảnh báo `NOT_SUPPORTED_YET`) → chạy `consolidate {"all": true}` sau khi xong M11.

### 3.5. Mở rộng dữ liệu thuế hộ kinh doanh

- Bổ sung seed số hiệu + từ khóa (`thuế khoán`, `cá nhân kinh doanh`, `kê khai`…) vào `crawl_source.config`; chạy crawl; theo dõi pipeline đến `INDEXED`.
- Ước lượng số ứng viên phải duyệt → lập kế hoạch với chuyên gia (2 giờ/tuần).

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M11-T1 | OCR engine + render + image worker | 3.1 | 02.1, 02.2 | 1.5 ngày |
| M11-T2 | Gộp OCR vào chuẩn hóa + kiểm tra chất lượng | 3.1 | 02.8, 02.9 | 0.5 ngày |
| M11-T3 | Tầng LLM F04 + prompt + hậu kiểm | 3.2 | 04.2, 04.3, 04.11 | 1.5 ngày |
| M11-T4 | Phân loại chủ đề / đối tượng bằng LLM | 3.3 | 04.14, 04.15 | 0.5 ngày |
| M11-T5 | Hợp nhất cấp Điểm + `BO_SUNG` + sửa cả Điều | 3.4 | 06.9 + F06 §1.2 | 2 ngày |
| M11-T6 | Nạp mảng thuế hộ kinh doanh + chạy lại toàn pipeline | 3.5 | 01.2 | 1 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Tích hợp OCR | 1 PDF scan mẫu → có text, `ocr_pages`, `ocr_confidence_avg`; ảnh chất lượng kém → `NEEDS_ATTENTION` |
| Unit LLM (mock) | Câu khó → `RelationLLMResponse` hợp lệ → đúng ID qua `legal/refs`; LLM trả số hiệu không có trong câu → bị bỏ; JSON sai 3 lần → `manual_required` |
| Đo | Precision / recall tầng LLM trên tập câu "khó" của M04-T1 (ghi số, so với luật mẫu) |
| Unit `apply` | Sửa điểm `b`; bổ sung điểm `đ1` sau `đ`; bãi bỏ điểm `a`; điểm không tồn tại; Điều `9a` mới |
| Property-based | Chuỗi sự kiện ngẫu nhiên trộn cấp Điểm / Khoản → bất biến không chồng lấn vẫn đúng |
| Tích hợp | F13 kiểm tra Điểm đã bãi bỏ → `het_hieu_luc` (BR-13.2) |
| Hồi quy | Golden M09 vẫn xanh sau khi chạy lại toàn pipeline |

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| PaddleOCR nặng, cài khó trên Windows | Chạy trong container Linux riêng; Tesseract là đường dự phòng nhẹ |
| Thời gian trích xuất LLM dài (Qwen local) | Chỉ câu có trigger; batch 5 câu; chạy ngoài giờ; nhường chat |
| Tách điểm sai làm hỏng phiên bản Khoản | Kiểm tra `diem[]` sau áp phải bằng kỳ vọng; lệch → cảnh báo, không ghi |
| Số ứng viên tăng vượt ngân sách duyệt | Ưu tiên văn bản phục vụ bộ đánh giá; bulk-approve |

## 7. Bàn giao

- Sau M11: mọi văn bản MVP `INDEXED`, cạnh chủ đề / đối tượng đủ để M12 (Leiden), M14 (lọc đồ thị theo chủ đề + đối tượng) dùng.
