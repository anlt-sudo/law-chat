# M01 – LLM Gateway · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F17](../../features/F17-llm-gateway.md)

## Chuẩn bị

- [ ] LM Studio đã nạp `qwen3.5-9b` (GGUF Q4_K_M) và `bge-m3`, bật Local Server cổng 1234
- [ ] `curl {LLM_BASE_URL}/models` từ trong container backend trả 2 model

## Triển khai

- [ ] M01-T1 Spike LM Studio, ghi kết quả `docs/spikes/lmstudio.md`:
  - [ ] Cách tắt thinking hoạt động (`enable_thinking` / `/no_think`)
  - [ ] `response_format json_schema` có / không được hỗ trợ
  - [ ] `usage.prompt_tokens` có trả về; hệ số ký tự / token đo được
  - [ ] Độ trễ trung bình chat và embedding trên máy dev
- [ ] M01-T2 Mock LM Studio đủ kịch bản (JSON sai, think cắt ngang, chậm, 500, tắt, thiếu model)
- [ ] M01-T3 `profiles.py` đủ 8 tác vụ F17 §1.1; `errors.py`; `tokens.py`
- [ ] M01-T4 `strip_think` + `ThinkStreamFilter`
- [ ] M01-T5 `PrioritySemaphore` (chat / embedding tách riêng) + bảng `runtime_flag` + `wait_if_interactive_busy()`
- [ ] M01-T6 Retry lỗi kết nối 2 lần (1 s, 3 s); không retry timeout tác vụ tương tác; circuit breaker
- [ ] M01-T7 `complete_json`, `complete_text`, `stream_text`, `embed`
- [ ] M01-T8 Health check 30 s; cảnh báo `LLM_BASE_URL` public + không https; ghi `llm_call_log`
- [ ] M01-T9 `/admin/llm/health`, `/admin/llm/stats`, `/admin/llm/config` (ẩn key)
- [ ] Migration `0002_llm` (`llm_call_log`, `runtime_flag`)
- [ ] Không file nào ngoài `app/llm/` import `openai` (thêm rule `ruff` banned-api hoặc test grep)

## Kiểm thử

- [ ] Unit `strip_think`, `ThinkStreamFilter` (thẻ cắt ngang delta, `<` lẻ)
- [ ] Unit hàng đợi ưu tiên: ưu tiên 1 vượt ưu tiên 3 đang chờ
- [ ] Unit circuit breaker
- [ ] Tích hợp mock: JSON sai 2 lần rồi đúng; sai 3 lần → `LLMOutputError`
- [ ] Tích hợp mock: `ContextTooLong` không gửi request
- [ ] Tích hợp mock: sai số chiều embedding → lỗi

## Tiêu chí chấp nhận (F17 §7)

- [ ] `curl {LLM_BASE_URL}/models` và `/admin/llm/health` cùng báo hai model đã nạp
- [ ] Thinking tắt → không có `<think>` trong output `extract_relations`; thinking bật → stream không chứa nội dung think (kể cả thẻ cắt ngang delta)
- [ ] Mock trả JSON sai 2 lần rồi đúng → `complete_json` thành công, `attempts = 3`
- [ ] Tắt LM Studio → sau 5 lỗi mạch mở, lời gọi tiếp theo trả `LLMUnavailable` trong < 50 ms
- [ ] Batch ưu tiên 3 đang chạy → câu hỏi chat mới được phục vụ trước các lời gọi batch đang chờ

## Definition of Done

- [ ] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module)
- [ ] `.env.example` có đủ biến F17 §6.1 + `THINKING_MODE`, `LLM_CHARS_PER_TOKEN`
