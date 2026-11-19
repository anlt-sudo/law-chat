# M01 – LLM Gateway · Checklist

Plan: [implement-plan.md](implement-plan.md) · Feature: [F17](../../features/F17-llm-gateway.md)

> Trạng thái 19/11/2026: đã triển khai, kiểm tra bằng mock và LM Studio thật (DeepSeek R1 0528 Qwen3 8B + nomic-embed-text v1.5). Khác plan: gọi LM Studio bằng `httpx` thay cho OpenAI SDK (đọc được `reasoning_content`, `/api/v0/models`); ghi đè timeout bằng một biến JSON `LLM_TIMEOUTS` thay cho `LLM_TIMEOUT_<TASK>`.

## Chuẩn bị

- [x] LM Studio có model chat + embedding, Local Server chạy (cổng **1235**) *(model thực tế khác đặc tả – xem M01 §2b)*
- [x] `curl {LLM_BASE_URL}/models` từ container backend trả 2 model *(qua `host.docker.internal:1235`)*

## Triển khai

- [x] M01-T1 Spike LM Studio → [docs/spikes/lmstudio.md](../../spikes/lmstudio.md):
  - [x] Cách tắt thinking: **không cách nào hoạt động** với DeepSeek R1 → `THINKING_MODE=none`
  - [x] `response_format json_schema` được hỗ trợ (ép đúng cú pháp)
  - [x] `usage` có `prompt_tokens`, `completion_tokens`, `reasoning_tokens`
  - [x] Độ trễ: ~7 token/s; chat 25–80 s; embedding ~3 s
  - [x] Phát hiện thêm: LM Studio chỉ giữ 1 model khi JIT → health cảnh báo
- [x] M01-T2 Mock LM Studio (`tests/mocks/lmstudio_mock.py`): JSON sai, think cắt ngang delta, `reasoning_content`, hết token khi đang suy nghĩ, 5xx, timeout, tắt, thiếu model, không có `/api/v0`
- [x] M01-T3 `profiles.py` đủ 8 tác vụ; `errors.py`; `tokens.py`
- [x] M01-T4 `split_think` / `strip_think` + `ThinkStreamFilter`; đọc `reasoning_content`
- [x] M01-T5 `PrioritySemaphore` (chat / embedding tách riêng) + bảng `runtime_flag` + `wait_until_idle()`; tác vụ tương tác ghi cờ ngay khi bắt đầu + heartbeat
- [x] M01-T6 Retry lỗi kết nối / 5xx 2 lần (1 s, 3 s); không retry timeout; timeout không tính vào circuit; circuit breaker
- [x] M01-T7 `complete_json` / `complete_json_full`, `complete_text`, `stream_text`, `embed` (tiền tố nomic theo `kind`, lô 32, kiểm tra số chiều + context 2048)
- [x] M01-T7 Cộng `LLM_REASONING_BUDGET` vào `max_tokens`; `content` rỗng + `finish_reason=length` → `REASONING_TRUNCATED`
- [x] M01-T8 Health check 30 s (lifespan app); `/api/v0/models` → model đang nạp + context thực tế; cảnh báo URL public không https; ghi `llm_call_log` bất đồng bộ
- [x] M01-T9 `/admin/llm/health` (`?refresh=true`), `/admin/llm/stats`, `/admin/llm/config` (ẩn key) – yêu cầu `quan_tri`
- [x] Migration `0002_llm` (`llm_call_log` + cột `reasoning_tokens`, `runtime_flag`); `alembic check` không lệch
- [x] Không file nào ngoài `app/llm/` gọi LM Studio (test `test_llm_boundary.py`)

## Kiểm thử

- [x] Unit `split_think`, `ThinkStreamFilter` (thẻ cắt ngang delta, từng ký tự, `<` lẻ, khối chưa đóng)
- [x] Unit hàng đợi ưu tiên (ưu tiên 1 vượt ưu tiên 3 đang chờ; FIFO cùng ưu tiên; hủy không rò slot)
- [x] Unit circuit breaker (mở, half-open 1 yêu cầu thử, đóng lại, cửa sổ 60 s)
- [x] Mock: JSON sai 2 lần rồi đúng; sai 3 lần → `LLMOutputError(JSON_INVALID)`; chế độ `prompt`
- [x] Mock: `ContextTooLong` không gửi request; lỗi context từ LM Studio → `ContextTooLong`
- [x] Mock: sai số chiều embedding → `EMBEDDING_DIM_MISMATCH`
- [x] Tích hợp PG: `llm_call_log`, `runtime_flag` dùng chung giữa 2 "process", API admin + phân quyền
- [x] LM Studio thật (`RUN_LMSTUDIO=1`): 4/4 qua

Kết quả: 140 test qua (+4 test LM Studio thật chạy riêng); `ruff`, `mypy` sạch.

## Tiêu chí chấp nhận (F17 §7)

- [x] `curl {LLM_BASE_URL}/models` và `/admin/llm/health` cùng báo hai model *(health trên backend Docker: `status ok`, cả 2 model `ok`)*
- [x] Không có `<think>` trong output `extract_relations`; stream không chứa nội dung suy nghĩ (kể cả thẻ cắt ngang delta) *(mock + LM Studio thật)*
- [x] Mock trả JSON sai 2 lần rồi đúng → `complete_json` thành công, `attempts = 3`
- [x] Tắt LM Studio → sau 5 lỗi mạch mở, lời gọi tiếp theo trả `LLMUnavailable` < 50 ms *(mock `ConnectError`)*
- [x] Batch ưu tiên 3 đang chạy → câu hỏi chat được phục vụ trước các lời gọi batch đang chờ *(trong process: semaphore; giữa process: cờ `runtime_flag`)*

## Definition of Done

- [x] Theo [development-plan §7](../../development-plan.md#7-định-nghĩa-xong-chung-cho-mọi-module) *(trừ CI – chưa push)*
- [x] `.env.example` có đủ biến F17 §6.1 + `THINKING_MODE`, `LLM_JSON_MODE`, `LLM_REASONING_BUDGET`, `LLM_CHARS_PER_TOKEN`, `LLM_TIMEOUTS`

## Còn mở

- [ ] Nạp sẵn cả 2 model trong LM Studio (tắt tự gỡ model JIT) – nếu không, mỗi lần xen kẽ chat / embedding phải nạp lại model
- [ ] Kiểm tra GPU offload (7 token/s)
- [ ] Đo `LLM_CHARS_PER_TOKEN` thực tế cho văn bản pháp luật (spike: 18 token cho câu 44 ký tự ≈ 2.4) khi có dữ liệu M02/M03
