# Spike M01-T1 – LM Studio trên máy dev (18/11/2026)

Model thực tế khác inception (Qwen3.5 9B + bge-m3):

| Vai trò | Model | Thông số |
|---|---|---|
| Chat / trích xuất / tóm tắt | `deepseek-r1-0528-qwen3-8b` | GGUF Q4_K_M, kiến trúc qwen3, context tối đa 131 072 |
| Embedding | `text-embedding-nomic-embed-text-v1.5` | GGUF Q4_K_M, **768 chiều**, context 2 048 |

LM Studio ở `http://localhost:1235/v1` (không phải cổng mặc định 1234). Model ở trạng thái `not-loaded` → LM Studio nạp khi có request đầu tiên (JIT).

## Kết quả đo

| # | Thử | Kết quả |
|---|---|---|
| 1 | Chat tiếng Việt ("hóa đơn điện tử là gì?") | 64.8 s, 455 token ra, trong đó **307 token suy nghĩ**. Tiếng Việt trôi chảy, nội dung chung chung (không dẫn văn bản – đúng, vì chưa có ngữ cảnh) |
| 2 | `response_format: json_schema` (strict) | JSON **hợp lệ cú pháp** và đúng enum, nhưng **sai nghĩa**: câu "Bãi bỏ khoản 10 Điều 3…" bị gán `HUONG_DAN`; trường `van_ban_dich` chứa cả đoạn diễn giải dài. 79.4 s |
| 3 | Tắt thinking bằng `/no_think` | **Không có tác dụng**: vẫn 225 token suy nghĩ cho "1+1" (31.3 s) |
| 4 | Tắt thinking bằng `chat_template_kwargs.enable_thinking=false` | **Không có tác dụng**: vẫn 198 token suy nghĩ (27.2 s) |
| 5 | Embedding | 768 chiều. cos("Hủy hóa đơn điện tử", "Thủ tục hủy hóa đơn lập sai") = 0.810; với câu không liên quan ("Thuế thu nhập cá nhân") = 0.694 → **khoảng cách phân biệt hẹp**; có dấu / không dấu = 0.822 |

Tốc độ sinh ≈ **7 token/s**. Có thể một phần model đang chạy trên CPU, cần xem lại cài đặt GPU offload trong LM Studio.

## Ảnh hưởng tới đặc tả

| Điểm trong đặc tả | Thực tế với model này | Đề xuất |
|---|---|---|
| F17 BR-17.2 – tắt thinking cho tác vụ batch / JSON | DeepSeek R1 distill **luôn** suy nghĩ; cả 2 cách tắt đều không hoạt động | Bỏ chỉ thị tắt thinking cho model này (`THINKING_MODE=none`); tính ~200–350 token suy nghĩ vào mọi timeout và ngân sách token |
| F17 BR-17.4 – lọc `<think>` | LM Studio **đã tách** suy nghĩ ra `message.reasoning_content`; `content` không chứa `<think>` | Gateway đọc `reasoning_content` (lưu trace khi `TRACE_THINKING`); vẫn giữ `strip_think` cho `content` để phòng cấu hình LM Studio khác |
| F17 BR-17.3 – ép JSON | `json_schema` được LM Studio ép đúng cú pháp | Giữ; chất lượng ngữ nghĩa kém → củng cố quyết định **luật mẫu trước, LLM sau, bắt buộc duyệt** (F04, F05) |
| F08 BR-08.4 – P95 ≤ 10 s; F09 `query_analysis` timeout 1.5 s | Ở 7 token/s, chỉ riêng phần suy nghĩ đã mất ~30 s | **KPI P95 ≤ 10 s không đạt được** với cấu hình này. F09 phải chạy bằng quy tắc (đã có phương án BR-09.9); câu trả lời chat cần stream (M15) và timeout cứng 30 s (BR-08.5) gần như luôn bị chạm |
| F07 / F11 – bge-m3 1024 chiều | nomic 768 chiều, tiếng Việt yếu | Khuyến nghị tải **bge-m3** (GGUF) vào LM Studio. Nếu dùng nomic: đổi `EMBEDDING_DIM=768` và tạo lại vector index Neo4j (BR-07.4); với nomic nên thêm tiền tố `search_query:` / `search_document:` |

## Quyết định (19/11/2026)

1. **Giữ** DeepSeek R1 0528 Qwen3 8B làm model chat.
2. **Dùng** nomic-embed-text v1.5 (768 chiều). Đã áp dụng: `EMBEDDING_DIM=768`, vector index Neo4j tạo lại ở 768 chiều, thêm biến tiền tố `search_query:` / `search_document:`.
3. Điều chỉnh plan: M01 §2b, khối "Ảnh hưởng của model thực tế" ở M09, M12, M13, M15.

Hệ quả đã chấp nhận: KPI P95 ≤ 10 s (inception §7) không đạt với cấu hình này; LLM phân tích câu hỏi tắt mặc định.

## Câu hỏi ban đầu

1. Giữ DeepSeek R1 0528 Qwen3 8B hay chuyển sang một model cho phép tắt thinking (Qwen3 / Qwen3.5 instruct)? Model "luôn suy nghĩ" làm mọi bước LLM chậm gấp nhiều lần.
2. Embedding: tải bge-m3 (khuyến nghị) hay chấp nhận nomic 768 chiều?
3. Kiểm tra GPU offload trong LM Studio (tốc độ 7 token/s là thấp với model 8B Q4 trên GPU). *(chưa trả lời)*
