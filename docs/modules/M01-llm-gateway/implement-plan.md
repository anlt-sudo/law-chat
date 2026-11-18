# M01 – LLM Gateway · Implement plan

| Mục | Nội dung |
|---|---|
| Feature | [F17 – LLM Gateway](../../features/F17-llm-gateway.md) |
| Giai đoạn | PoC – tuần 1 |
| Ước lượng | 2–3 ngày |
| Phụ thuộc | M00 |
| Module dùng kết quả | M04, M09, M11, M12, M13, M14, M15, M17 |
| Checklist | [checklist.md](checklist.md) |

---

## 1. Mục tiêu

Một module duy nhất (`app/llm`) bọc mọi lời gọi tới LM Studio: hồ sơ tác vụ, bật / tắt thinking, lọc `<think>`, ép JSON theo Pydantic, ưu tiên chat hơn batch, circuit breaker, health check, ghi log. Không code nào khác được import OpenAI SDK (BR-17.1).

## 2. Phạm vi

| Trong M01 | Ngoài M01 |
|---|---|
| Toàn bộ F17: `complete_json`, `complete_text`, `stream_text`, `embed`, `health` | Prompt nghiệp vụ (thuộc từng module gọi) |
| Hàng đợi ưu tiên + semaphore trong process; cờ `interactive_busy` dùng chung giữa process | Trang quản trị giao diện (M10 đợt 2) |
| Mock LM Studio cho test / CI | |
| API quản trị `/admin/llm/*` | |

## 2b. Model thực tế (quyết định 19/11/2026)

Máy dev dùng **DeepSeek R1 0528 Qwen3 8B** (chat) và **nomic-embed-text v1.5** (embedding, 768 chiều) thay cho Qwen3.5 9B + bge-m3 – kết quả đo ở [docs/spikes/lmstudio.md](../../spikes/lmstudio.md). Điều chỉnh so với F17:

| Điểm F17 | Điều chỉnh |
|---|---|
| BR-17.2 tắt thinking | Model **luôn suy nghĩ**, không tắt được (`/no_think`, `enable_thinking` đều vô hiệu). Thêm `THINKING_MODE=none\|template\|soft_switch` (mặc định `none` cho model này): gateway không chèn chỉ thị; `TaskProfile.thinking` chỉ còn ý nghĩa "có lưu suy nghĩ vào trace hay không" |
| BR-17.4 lọc `<think>` | LM Studio trả suy nghĩ ở `message.reasoning_content` (stream: `delta.reasoning_content`), `content` sạch. Gateway đọc `reasoning_content` khi `return_thinking=True`; vẫn chạy `strip_think` / `ThinkStreamFilter` trên `content` để an toàn khi đổi model / cấu hình |
| BR-17.13 token | Cộng thêm `LLM_REASONING_BUDGET` (mặc định 600 token) vào `max_tokens` của mọi tác vụ, nếu không model hết token khi còn đang suy nghĩ → `content` rỗng. `content` rỗng + `finish_reason = length` → lỗi `LLMOutputError("REASONING_TRUNCATED")` |
| Timeout bảng 1.1 | Đo được ~7 token/s → mọi timeout cấu hình được qua env `LLM_TIMEOUT_<TASK>`; mặc định dev: `chat_answer` 180 s, `query_analysis` tắt (xem M09/M15), `global_map` 120 s, `extract_relations` 300 s, `classify_topics` 180 s, `summarize_cluster` 300 s, `judge` 180 s |
| `embed` | Thêm tiền tố nomic: `EMBEDDING_QUERY_PREFIX` ("search_query: ") cho truy vấn, `EMBEDDING_DOCUMENT_PREFIX` ("search_document: ") cho lập chỉ mục – tham số `kind: Literal["query","document"]` của `embed()`. Kiểm tra mỗi đầu vào ≤ `EMBEDDING_CONTEXT_TOKENS` (2048) |
| BR-17.10 health | `/v1/models` liệt kê cả model chưa nạp (`state: not-loaded` ở `/api/v0/models`). Health báo thêm `loaded: bool` lấy từ `/api/v0/models` (API riêng của LM Studio, bỏ qua nếu không có) |
| Mock LM Studio (M01-T2) | Mock trả `reasoning_content` + `content`, và kịch bản hết token khi đang suy nghĩ |

## 3. Thiết kế

### 3.1. Cấu trúc file

```text
backend/app/llm/
├── __init__.py          # get_gateway() – singleton theo process
├── errors.py            # LLMUnavailable, LLMTimeout, LLMOutputError, ContextTooLong
├── profiles.py          # TaskName, TaskProfile, PROFILES (bảng F17 §1.1)
├── think_filter.py      # strip_think(text), ThinkStreamFilter (máy trạng thái)
├── tokens.py            # estimate_tokens(messages)
├── priority.py          # PrioritySemaphore (heap theo (priority, seq))
├── circuit.py           # CircuitBreaker (5 lỗi / 60 s → mở 30 s → half-open)
├── busy_flag.py         # mark_interactive(), is_interactive_busy() qua bảng runtime_flag
├── client.py            # AsyncOpenAI(base_url, api_key, timeout)
├── gateway.py           # LLMGateway – hiện thực Protocol F17 §5.1
├── health.py            # vòng health check 30 s, HealthStatus
├── call_log.py          # ghi llm_call_log (bất đồng bộ, không chặn caller)
└── router.py            # /api/v1/admin/llm/health | stats | config
backend/tests/mocks/lmstudio_mock.py   # FastAPI giả lập /v1/models, /chat/completions, /embeddings
```

### 3.2. Hồ sơ tác vụ

```python
class TaskProfile(BaseModel):
    thinking: bool | Literal["config"]   # "config" → đọc CHAT_THINKING
    temperature: float
    timeout_s: float
    priority: Literal[1, 2, 3]
    interactive: bool                     # True → không retry timeout (BR-17.8)

PROFILES = {
    "chat_answer":       TaskProfile(thinking="config", temperature=0.1, timeout_s=30,  priority=1, interactive=True),
    "query_analysis":    TaskProfile(thinking=False,    temperature=0.0, timeout_s=1.5, priority=1, interactive=True),
    "global_map":        TaskProfile(thinking=False,    temperature=0.1, timeout_s=15,  priority=2, interactive=True),
    "extract_relations": TaskProfile(thinking=False,    temperature=0.1, timeout_s=60,  priority=3, interactive=False),
    "classify_topics":   TaskProfile(thinking=False,    temperature=0.0, timeout_s=30,  priority=3, interactive=False),
    "summarize_cluster": TaskProfile(thinking=False,    temperature=0.2, timeout_s=120, priority=3, interactive=False),
    "judge":             TaskProfile(thinking=False,    temperature=0.0, timeout_s=60,  priority=3, interactive=False),
}
```

### 3.3. Quyết định kỹ thuật

| Vấn đề | Quyết định |
|---|---|
| Tắt thinking (BR-17.2) | Spike M01-T1 kiểm tra 2 cách: (a) `extra_body={"chat_template_kwargs": {"enable_thinking": false}}`, (b) thêm `/no_think` cuối tin nhắn user. Chọn cách hoạt động trên bản LM Studio đang dùng, đặt trong `THINKING_MODE=template\|soft_switch`. Luôn chạy `strip_think` sau đó |
| Ép JSON (BR-17.3) | `response_format={"type":"json_schema","json_schema":{"name":…,"schema":Model.model_json_schema(),"strict":true}}`. Nếu spike cho thấy LM Studio không hỗ trợ → fallback: mô tả schema trong system prompt + `json.loads` phần `{…}` đầu tiên |
| Ước lượng token (BR-17.13) | Không có tokenizer Qwen offline → `ceil(len(text) / 2.5)` cho tiếng Việt + 10 token mỗi message; cộng `max_tokens` dự kiến; so với `LLM_CONTEXT_TOKENS`. Hệ số chỉnh được qua `LLM_CHARS_PER_TOKEN`; spike đo bằng `usage.prompt_tokens` thực tế |
| Ưu tiên giữa process (BR-17.7) | Semaphore + heap chỉ có tác dụng trong một process. **(bổ sung)** bảng `runtime_flag(key, value_ts)`: process API ghi `interactive_busy_until = now() + 10 s` mỗi khi bắt đầu / đang stream tác vụ ưu tiên 1; worker batch gọi `await wait_if_interactive_busy()` trước mỗi lời gọi ưu tiên 3. LM Studio tự xếp hàng các request đồng thời nên đây là cơ chế nhường, không phải khóa cứng |
| Đồng thời (BR-17.5) | `LLM_MAX_CONCURRENCY` (mặc định 1) cho chat, `EMBED_MAX_CONCURRENCY` (mặc định 2) cho embedding, tách riêng |
| Ghi log (BR-17.11) | Ghi `llm_call_log` qua task nền (`asyncio.create_task`) để không cộng độ trễ; lỗi ghi log chỉ cảnh báo |
| Cảnh báo bảo mật (BR-17.12) | Khi khởi động: host của `LLM_BASE_URL` không thuộc `localhost`, `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `host.docker.internal` và không phải `https` → log `WARNING` + đưa vào `health.warnings` |

### 3.4. Lọc `<think>` khi stream

`ThinkStreamFilter.feed(delta) -> (visible: str, thinking: str)` giữ bộ đệm `pending` cho trường hợp thẻ bị cắt giữa các delta (`"<thi"` + `"nk>"`). Trạng thái `Outside | Inside`; khi `Outside` mà phần cuối delta là tiền tố của `<think>` thì giữ lại trong `pending`, không phát. `flush()` khi kết thúc stream: `Inside` → bỏ phần còn lại; `pending` không thành thẻ → phát ra.

### 3.5. Schema PostgreSQL (migration `0002_llm`)

- `llm_call_log` đúng F17 §6.2.
- **(bổ sung)** `runtime_flag (key TEXT PRIMARY KEY, value_ts TIMESTAMPTZ, updated_at TIMESTAMPTZ DEFAULT now())`.

### 3.6. API quản trị

Theo F17 §5.2. `/stats` tính P50 / P95 bằng `percentile_cont` trên `llm_call_log` trong khoảng `from`–`to` (mặc định 24 giờ), nhóm theo `task`; `json_retry_rate = avg(attempts > 1)`.

## 4. Các bước triển khai

| Mã | Công việc | Chi tiết | BR | Ước lượng |
|---|---|---|---|---|
| M01-T1 | Spike LM Studio | Nạp `qwen3.5-9b` (Q4_K_M) + `bge-m3`; đo: cách tắt thinking nào hoạt động, `response_format json_schema` có được hỗ trợ không, `usage` có trả về không, stream có tách thẻ think thành nhiều delta không, độ trễ thực tế, embedding đúng 1024 chiều. Ghi kết quả vào `docs/spikes/lmstudio.md` | 17.2, 17.3 | 0.5 ngày |
| M01-T2 | Mock LM Studio | Mock hỗ trợ kịch bản: trả JSON sai N lần, chèn `<think>` cắt ngang delta, chậm X giây, trả 500, tắt hẳn (connection refused), `/v1/models` thiếu model | – | 0.5 ngày |
| M01-T3 | Profiles, errors, tokens | Như 3.2, 3.3 | 17.1, 17.13 | 0.25 ngày |
| M01-T4 | `think_filter` | `strip_think` (cả khối chưa đóng ở cuối) + `ThinkStreamFilter` | 17.4 | 0.25 ngày |
| M01-T5 | Ưu tiên, semaphore, busy flag | `PrioritySemaphore`, `runtime_flag`, `wait_if_interactive_busy()` | 17.5–17.7 | 0.5 ngày |
| M01-T6 | Circuit breaker + retry | Lỗi kết nối / 5xx: retry 2 lần (1 s, 3 s); tác vụ `interactive` bị timeout → ném `LLMTimeout` ngay | 17.8, 17.9 | 0.25 ngày |
| M01-T7 | `LLMGateway` | `complete_json` (vòng tối đa `LLM_JSON_MAX_ATTEMPTS`, lần sau thêm message lỗi validate), `complete_text`, `stream_text`, `embed` (lô ≤ 32, kiểm tra `EMBEDDING_DIM`) | 17.2–17.4, 17.13 | 0.5 ngày |
| M01-T8 | Health + log | Vòng health 30 s chạy trong lifespan của app và worker; `call_log` | 17.10–17.12 | 0.25 ngày |
| M01-T9 | API quản trị | 3 endpoint; `config` ẩn `LLM_API_KEY` | – | 0.25 ngày |

## 5. Kế hoạch test

| Loại | Nội dung |
|---|---|
| Unit | `strip_think`: không thẻ / 1 khối / nhiều khối / khối chưa đóng |
| Unit | `ThinkStreamFilter`: thẻ mở cắt `"<th"`+`"ink>"`, thẻ đóng cắt, `<` đơn lẻ không phải thẻ phải được phát ra |
| Unit | `PrioritySemaphore`: 3 tác vụ ưu tiên 3 đang chờ, 1 tác vụ ưu tiên 1 đến sau → được chạy trước |
| Unit | `CircuitBreaker`: 5 lỗi → mở; trong 30 s trả `LLMUnavailable` < 50 ms; sau 30 s half-open |
| Tích hợp (mock) | JSON sai 2 lần rồi đúng → thành công, log `attempts = 3`; sai 3 lần → `LLMOutputError` |
| Tích hợp (mock) | Message vượt context → `ContextTooLong`, không gọi HTTP |
| Tích hợp (mock) | Embedding trả 768 chiều trong khi cấu hình 1024 → lỗi rõ ràng |
| Thủ công (LM Studio thật) | `/admin/llm/health` báo 2 model; `extract_relations` không chứa `<think>`; chat stream không lộ think |

Test với LM Studio thật đánh dấu `@pytest.mark.lmstudio`, không chạy trong CI.

## 6. Rủi ro & lưu ý

| Rủi ro | Xử lý |
|---|---|
| Qwen3.5 không tôn trọng `/no_think` / `enable_thinking` | Vẫn lọc `<think>` (BR-17.4); đo độ trễ tăng thêm; nếu quá chậm cho batch thì cân nhắc model không-thinking cho tác vụ batch |
| LM Studio không hỗ trợ `json_schema` | Fallback prompt + parse (3.3); số lần gọi lại tăng → theo dõi `json_retry_rate` |
| Timeout 1.5 s của `query_analysis` quá chặt trên máy dev | Cấu hình được; F09 đã có phương án không cần LLM (BR-09.9) |
| Đồng hồ health check chạy ở mỗi process | Chấp nhận ở bản dev (2 process) |

## 7. Bàn giao

- Module khác dùng `from app.llm import get_gateway`; tác vụ mới phải thêm vào `PROFILES` trước.
- Worker batch (M04, M11, M12, M17) gọi `wait_if_interactive_busy()` giữa các lô.
- API chat (M09, M15) gọi `mark_interactive()` khi bắt đầu lượt hỏi đáp.
