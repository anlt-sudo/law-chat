"""LLM Gateway – cổng duy nhất tới LM Studio (F17). Không module nào khác gọi LM Studio trực tiếp.

Gọi qua HTTP (httpx) theo API chuẩn OpenAI của LM Studio thay vì OpenAI SDK để đọc được các
trường riêng (`reasoning_content`, `/api/v0/models`) và kiểm soát retry / timeout.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm.busy_flag import BusyFlag, MemoryBusyFlag, wait_until_idle
from app.llm.call_log import CallLogSink, CallRecord, MemorySink
from app.llm.circuit import CircuitBreaker
from app.llm.errors import ContextTooLong, LLMError, LLMOutputError, LLMTimeout, LLMUnavailable
from app.llm.priority import PrioritySemaphore
from app.llm.profiles import TaskProfile, get_profile
from app.llm.think_filter import ThinkStreamFilter, split_think
from app.llm.tokens import estimate_messages_tokens, estimate_text_tokens

logger = logging.getLogger(__name__)

Message = dict[str, Any]
EmbedKind = Literal["query", "document"]

INTERACTIVE_MARK_S = 15.0
INTERACTIVE_HEARTBEAT_S = 5.0
_CONTEXT_ERR_RE = re.compile(r"context|n_ctx|too long|exceed", re.IGNORECASE)


# ---------------------------------------------------------------- kết quả


class Usage(BaseModel):
    tokens_in: int | None = None
    tokens_out: int | None = None
    reasoning_tokens: int | None = None


class TextResult(BaseModel):
    text: str
    thinking: str | None = None
    finish_reason: str | None = None
    usage: Usage = Usage()
    latency_ms: int = 0
    queue_ms: int = 0


@dataclass
class JsonResult[T: BaseModel]:
    value: T
    attempts: int
    thinking: str | None = None
    usage: Usage = field(default_factory=Usage)


class StreamDelta(BaseModel):
    text: str = ""
    thinking: str = ""  # chỉ có khi return_thinking=True
    done: bool = False
    finish_reason: str | None = None
    usage: Usage | None = None


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "down"]
    base_url: str
    models_available: list[str] = []
    models_loaded: list[str] | None = None  # None khi LM Studio không có /api/v0/models
    llm_model: str
    embedding_model: str
    llm_model_ok: bool = False
    embedding_model_ok: bool = False
    loaded_context_length: int | None = None
    circuit: str = "closed"
    queue: dict[str, dict[str, int]] = {}
    last_check: datetime
    warnings: list[str] = []
    error: str | None = None


# ---------------------------------------------------------------- tiện ích


def security_warnings(base_url: str) -> list[str]:
    """BR-17.12: LM Studio HTTP không xác thực chỉ được mở trong mạng nội bộ."""
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if parts.scheme == "https" or host in ("localhost", "host.docker.internal"):
        return []
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback:
            return []
    except ValueError:
        pass  # tên miền – không chắc là nội bộ
    return [
        f"LLM_BASE_URL ({host}) không phải địa chỉ nội bộ và không dùng https – "
        "LM Studio không xác thực, chỉ nên mở trong mạng nội bộ hoặc sau reverse proxy HTTPS"
    ]


def parse_json_output[T: BaseModel](text: str, schema: type[T]) -> T:
    """Lấy JSON từ output (bỏ ```json fence, chữ thừa trước / sau) rồi validate bằng Pydantic."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
        if not starts:
            raise ValueError("Không tìm thấy JSON trong output") from None
        start = min(starts)
        end = max(s.rfind("}"), s.rfind("]"))
        if end <= start:
            raise ValueError("JSON không đóng") from None
        obj = json.loads(s[start : end + 1])
    return schema.model_validate(obj)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(x) for x in e['loc']) or '(gốc)'}: {e['msg']}" for e in exc.errors()[:5]
        )
    return str(exc)[:300]


def _outcome(exc: BaseException | None) -> str:
    match exc:
        case None:
            return "ok"
        case LLMTimeout():
            return "timeout"
        case LLMUnavailable():
            return "unavailable"
        case ContextTooLong():
            return "context_too_long"
        case LLMOutputError() if exc.code == "JSON_INVALID":
            return "json_error"
        case _:
            return "error"


def _usage(data: dict[str, Any]) -> Usage:
    u = data.get("usage") or {}
    details = u.get("completion_tokens_details") or {}
    return Usage(
        tokens_in=u.get("prompt_tokens"),
        tokens_out=u.get("completion_tokens"),
        reasoning_tokens=details.get("reasoning_tokens"),
    )


# ---------------------------------------------------------------- gateway


class LLMGateway:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        busy_flag: BusyFlag | None = None,
        call_log: CallLogSink | None = None,
        breaker: CircuitBreaker | None = None,
        retry_backoff_s: Sequence[float] = (1.0, 3.0),
    ) -> None:
        self.s = settings
        self.base_url = settings.llm_base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            transport=transport,
        )
        self._chat_sem = PrioritySemaphore(settings.llm_max_concurrency)
        self._embed_sem = PrioritySemaphore(settings.embed_max_concurrency)
        self.breaker = breaker or CircuitBreaker()
        self.busy: BusyFlag = busy_flag or MemoryBusyFlag()
        self.call_log: CallLogSink = call_log or MemorySink()
        self.retry_backoff_s = tuple(retry_backoff_s)
        self.last_health: HealthStatus | None = None
        self.static_warnings = security_warnings(self.base_url)
        for w in self.static_warnings:
            logger.warning(w)

    async def aclose(self) -> None:
        await self.call_log.flush()
        await self._http.aclose()

    # ------------------------------------------------------------ API công khai

    async def complete_text(
        self,
        task: str,
        messages: Sequence[Message],
        *,
        max_tokens: int | None = None,
        return_thinking: bool = False,
        caller_ref: str | None = None,
    ) -> TextResult:
        profile = get_profile(task, self.s)
        msgs = self._prepare_messages(profile, messages)
        payload = self._chat_payload(profile, msgs, max_tokens)
        started = time.monotonic()
        result: TextResult | None = None
        error: BaseException | None = None
        queue_ms = 0
        try:
            async with self._turn(profile) as waited:
                queue_ms = waited()
                data = await self._request_json(profile, "/chat/completions", payload)
            result = self._text_result(data, return_thinking)
            result.queue_ms = queue_ms
            result.latency_ms = int((time.monotonic() - started) * 1000)
            return result
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._log(
                profile, error=error, attempts=1, queue_ms=queue_ms, started=started,
                usage=result.usage if result else None, prompt=msgs,
                output=result.text if result else None, caller_ref=caller_ref,
            )  # fmt: skip

    async def complete_json[T: BaseModel](
        self,
        task: str,
        messages: Sequence[Message],
        schema: type[T],
        *,
        max_tokens: int | None = None,
        caller_ref: str | None = None,
    ) -> T:
        result = await self.complete_json_full(
            task, messages, schema, max_tokens=max_tokens, caller_ref=caller_ref
        )
        return result.value

    async def complete_json_full[T: BaseModel](
        self,
        task: str,
        messages: Sequence[Message],
        schema: type[T],
        *,
        max_tokens: int | None = None,
        caller_ref: str | None = None,
    ) -> JsonResult[T]:
        """BR-17.3: ép JSON theo schema, validate Pydantic.

        JSON lỗi → gọi lại kèm thông báo lỗi, tối đa LLM_JSON_MAX_ATTEMPTS lần.
        """
        profile = get_profile(task, self.s)
        msgs = self._prepare_messages(profile, messages)
        if self.s.llm_json_mode == "prompt":
            msgs = [_schema_instruction(schema), *msgs]
        started = time.monotonic()
        attempts = 0
        usage = Usage()
        last_text: str | None = None
        error: BaseException | None = None
        queue_ms = 0
        try:
            async with self._turn(profile) as waited:
                queue_ms = waited()
                last_exc: Exception | None = None
                while attempts < self.s.llm_json_max_attempts:
                    attempts += 1
                    payload = self._chat_payload(profile, msgs, max_tokens)
                    if self.s.llm_json_mode == "json_schema":
                        payload["response_format"] = _response_format(schema)
                    data = await self._request_json(profile, "/chat/completions", payload)
                    res = self._text_result(data, return_thinking=False)
                    usage = _sum_usage(usage, res.usage)
                    last_text = res.text
                    try:
                        value = parse_json_output(res.text, schema)
                    except (ValueError, ValidationError) as exc:
                        last_exc = exc
                        logger.info(
                            "JSON không hợp lệ, gọi lại",
                            extra={"task": task, "attempt": attempts, "error": _short_error(exc)},
                        )
                        msgs = [
                            *msgs,
                            {"role": "assistant", "content": res.text[:2000]},
                            {
                                "role": "user",
                                "content": (
                                    f"JSON trước không hợp lệ: {_short_error(exc)}. "
                                    "Chỉ trả về đúng một đối tượng JSON theo schema, "
                                    "không giải thích thêm."
                                ),
                            },
                        ]
                        continue
                    return JsonResult(value=value, attempts=attempts, usage=usage)
                raise LLMOutputError(
                    f"JSON không hợp lệ sau {attempts} lần: "
                    f"{_short_error(last_exc or ValueError())}",
                    code="JSON_INVALID",
                )
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._log(
                profile, error=error, attempts=max(attempts, 1), queue_ms=queue_ms,
                started=started, usage=usage, prompt=msgs, output=last_text,
                caller_ref=caller_ref,
            )  # fmt: skip

    async def stream_text(
        self,
        task: str,
        messages: Sequence[Message],
        *,
        max_tokens: int | None = None,
        return_thinking: bool = False,
        caller_ref: str | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """UC-17.2: phát từng delta đã lọc suy nghĩ. Dùng với `contextlib.aclosing(...)`."""
        profile = get_profile(task, self.s)
        msgs = self._prepare_messages(profile, messages)
        payload = self._chat_payload(profile, msgs, max_tokens)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        started = time.monotonic()
        deadline = started + profile.timeout_s
        flt = ThinkStreamFilter()
        visible_parts: list[str] = []
        usage: Usage | None = None
        finish: str | None = None
        error: BaseException | None = None
        queue_ms = 0
        try:
            async with self._turn(profile) as waited:
                queue_ms = waited()
                response = await self._request(profile, "/chat/completions", payload, stream=True)
                try:
                    async for line in response.aiter_lines():
                        if time.monotonic() > deadline:
                            raise LLMTimeout(f"{task}: quá {profile.timeout_s:.0f} s khi stream")
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        chunk = json.loads(raw)
                        if chunk.get("usage"):
                            usage = _usage(chunk)
                        for choice in chunk.get("choices") or []:
                            delta = choice.get("delta") or {}
                            visible, think = flt.feed(delta.get("content") or "")
                            think += delta.get("reasoning_content") or ""
                            finish = choice.get("finish_reason") or finish
                            if visible or (return_thinking and think):
                                visible_parts.append(visible)
                                yield StreamDelta(
                                    text=visible, thinking=think if return_thinking else ""
                                )
                except httpx.TimeoutException as exc:
                    raise LLMTimeout(f"{task}: LM Studio ngừng gửi dữ liệu") from exc
                except httpx.TransportError as exc:
                    self.breaker.record_failure()
                    raise LLMUnavailable(f"Mất kết nối LM Studio khi stream: {exc}") from exc
                finally:
                    await response.aclose()
            visible, _ = flt.flush()
            if visible:
                visible_parts.append(visible)
                yield StreamDelta(text=visible)
            if not "".join(visible_parts).strip() and finish == "length":
                raise LLMOutputError(
                    "Hết max_tokens khi model còn đang suy nghĩ", code="REASONING_TRUNCATED"
                )
            yield StreamDelta(done=True, finish_reason=finish, usage=usage)
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._log(
                profile, error=error, attempts=1, queue_ms=queue_ms, started=started,
                usage=usage, prompt=msgs, output="".join(visible_parts), caller_ref=caller_ref,
            )  # fmt: skip

    async def embed(
        self,
        texts: Sequence[str],
        *,
        kind: EmbedKind = "query",
        priority: Literal[1, 3] | None = None,
        caller_ref: str | None = None,
    ) -> list[list[float]]:
        """UC-17.3: lô ≤ EMBEDDING_BATCH_SIZE, tiền tố theo `kind` (nomic), kiểm tra số chiều."""
        base = get_profile("embed", self.s)
        prio = priority or (1 if kind == "query" else 3)
        profile = base.model_copy(update={"priority": prio, "interactive": prio == 1})
        prefix = (
            self.s.embedding_query_prefix if kind == "query" else self.s.embedding_document_prefix
        )
        inputs = [prefix + t for t in texts]
        for i, t in enumerate(inputs):
            n = estimate_text_tokens(t, self.s.llm_chars_per_token)
            if n > self.s.embedding_context_tokens:
                raise ContextTooLong(
                    f"Văn bản embedding #{i} ~{n} token > {self.s.embedding_context_tokens}"
                )
        started = time.monotonic()
        error: BaseException | None = None
        tokens_in = 0
        out: list[list[float]] = []
        try:
            size = max(1, self.s.embedding_batch_size)
            for start in range(0, len(inputs), size):
                batch = inputs[start : start + size]
                if prio == 3:
                    await wait_until_idle(self.busy)
                async with self._embed_sem.slot(prio):
                    data = await self._request_json(
                        profile, "/embeddings", {"model": self.s.embedding_model, "input": batch}
                    )
                rows = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
                vecs = [list(map(float, r["embedding"])) for r in rows]
                if len(vecs) != len(batch):
                    raise LLMOutputError(
                        f"Embedding trả {len(vecs)} vector cho {len(batch)} đầu vào",
                        code="EMBEDDING_COUNT_MISMATCH",
                    )
                bad = {len(v) for v in vecs if len(v) != self.s.embedding_dim}
                if bad:
                    raise LLMOutputError(
                        f"Embedding {sorted(bad)} chiều, cấu hình EMBEDDING_DIM="
                        f"{self.s.embedding_dim}",
                        code="EMBEDDING_DIM_MISMATCH",
                    )
                tokens_in += int((data.get("usage") or {}).get("prompt_tokens") or 0)
                out.extend(vecs)
            return out
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._log(
                profile, error=error, attempts=1, queue_ms=0, started=started,
                usage=Usage(tokens_in=tokens_in or None), prompt=None, output=None,
                caller_ref=caller_ref, model=self.s.embedding_model,
            )  # fmt: skip

    async def check_health(self) -> HealthStatus:
        """BR-17.10: model nào có, model nào đang nạp, context thực tế, cảnh báo."""
        warnings = list(self.static_warnings)
        status = HealthStatus(
            status="down",
            base_url=self.base_url,
            llm_model=self.s.llm_model,
            embedding_model=self.s.embedding_model,
            last_check=datetime.now(UTC),
        )
        try:
            r = await self._http.get("/models", timeout=5.0)
            r.raise_for_status()
            ids = [m["id"] for m in r.json().get("data", [])]
        except Exception as exc:
            status.error = f"{type(exc).__name__}: {exc}"[:300]
            status.warnings = warnings
            return self._finish_health(status)

        status.models_available = ids
        status.llm_model_ok = self.s.llm_model in ids
        status.embedding_model_ok = self.s.embedding_model in ids
        for ok, name, what in (
            (status.llm_model_ok, self.s.llm_model, "LLM_MODEL"),
            (status.embedding_model_ok, self.s.embedding_model, "EMBEDDING_MODEL"),
        ):
            if not ok:
                warnings.append(f"{what}={name} không có trong LM Studio")

        # API riêng của LM Studio: trạng thái nạp + context thực tế (bỏ qua nếu không có)
        try:
            root = self.base_url.removesuffix("/v1")
            r0 = await self._http.get(f"{root}/api/v0/models", timeout=5.0)
            if r0.status_code == 200:
                info = {m["id"]: m for m in r0.json().get("data", [])}
                status.models_loaded = [k for k, m in info.items() if m.get("state") == "loaded"]
                llm_info = info.get(self.s.llm_model, {})
                status.loaded_context_length = llm_info.get("loaded_context_length")
                loaded = {
                    n: n in status.models_loaded for n in (self.s.llm_model, self.s.embedding_model)
                }
                if not any(loaded.values()):
                    warnings.append("Chưa nạp model nào – lời gọi đầu tiên sẽ chậm (JIT load)")
                elif not all(loaded.values()):
                    missing = next(n for n, v in loaded.items() if not v)
                    warnings.append(
                        f"{missing} chưa nạp. Nếu LM Studio tự gỡ model JIT cũ khi nạp model mới, "
                        "xen kẽ chat / embedding sẽ nạp lại model mỗi lần – nên nạp sẵn cả hai"
                    )
                ctx = status.loaded_context_length
                if ctx is not None and ctx < self.s.llm_context_tokens:
                    warnings.append(
                        f"Context đang nạp ({ctx}) < LLM_CONTEXT_TOKENS "
                        f"({self.s.llm_context_tokens}) – giảm cấu hình hoặc nạp lại model"
                    )
        except Exception:
            logger.debug("Không đọc được /api/v0/models", exc_info=True)

        status.warnings = warnings
        status.status = "ok" if status.llm_model_ok and status.embedding_model_ok else "degraded"
        return self._finish_health(status)

    async def run_health_loop(self, stop: asyncio.Event) -> None:
        previous: str | None = None
        while not stop.is_set():
            health = await self.check_health()
            if health.status != previous:
                log = logger.info if health.status == "ok" else logger.warning
                log("LLM health", extra={"status": health.status, "warnings": health.warnings})
                previous = health.status
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.s.llm_health_interval_s)

    def runtime_state(self) -> dict[str, Any]:
        return {
            "circuit": self.breaker.state,
            "queue": {"chat": self._chat_sem.queue_sizes(), "embed": self._embed_sem.queue_sizes()},
        }

    # ------------------------------------------------------------ nội bộ

    def _finish_health(self, status: HealthStatus) -> HealthStatus:
        state = self.runtime_state()
        status.circuit = state["circuit"]
        status.queue = state["queue"]
        self.last_health = status
        return status

    def _prepare_messages(self, profile: TaskProfile, messages: Sequence[Message]) -> list[Message]:
        msgs = [dict(m) for m in messages]
        if not msgs:
            raise ValueError("messages rỗng")
        if self.s.thinking_mode == "soft_switch" and profile.thinking is False:
            for m in reversed(msgs):
                if m.get("role") == "user":
                    m["content"] = f"{m.get('content', '')} /no_think"
                    break
        return msgs

    def _chat_payload(
        self, profile: TaskProfile, msgs: list[Message], max_tokens: int | None
    ) -> dict[str, Any]:
        out_tokens = (max_tokens or profile.max_tokens) + self.s.llm_reasoning_budget
        prompt_tokens = estimate_messages_tokens(msgs, self.s.llm_chars_per_token)
        if prompt_tokens + out_tokens > self.s.llm_context_tokens:
            raise ContextTooLong(
                f"{profile.name}: prompt ~{prompt_tokens} + max_tokens {out_tokens} "
                f"> LLM_CONTEXT_TOKENS {self.s.llm_context_tokens}"
            )
        payload: dict[str, Any] = {
            "model": self.s.llm_model,
            "messages": msgs,
            "temperature": profile.temperature,
            "max_tokens": out_tokens,
        }
        if self.s.thinking_mode == "template" and profile.thinking is False:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    @contextlib.asynccontextmanager
    async def _turn(self, profile: TaskProfile) -> AsyncIterator[Any]:
        """Chờ lượt theo ưu tiên (BR-17.6, BR-17.7).

        Tác vụ tương tác giữ cờ interactive_busy; batch nhường trước khi xếp hàng.
        """
        t0 = time.monotonic()
        heartbeat: asyncio.Task[None] | None = None
        if profile.priority == 3:
            await wait_until_idle(self.busy)
        else:
            await self._mark_interactive()  # ghi ngay – lời gọi ngắn có thể xong trước nhịp đầu
            heartbeat = asyncio.create_task(self._heartbeat())
        try:
            async with self._chat_sem.slot(profile.priority):
                waited = int((time.monotonic() - t0) * 1000)
                yield lambda: waited
        finally:
            if heartbeat:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat

    async def _mark_interactive(self) -> None:
        try:
            await self.busy.mark(INTERACTIVE_MARK_S)
        except Exception:
            logger.warning("Không ghi được cờ interactive_busy", exc_info=True)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(INTERACTIVE_HEARTBEAT_S)
            await self._mark_interactive()

    async def _request(
        self, profile: TaskProfile, path: str, payload: dict[str, Any], *, stream: bool = False
    ) -> httpx.Response:
        """POST có retry lỗi kết nối / 5xx (BR-17.8) và circuit breaker (BR-17.9)."""
        timeout = httpx.Timeout(
            connect=5.0,
            read=min(profile.timeout_s, 60.0) if stream else profile.timeout_s,
            write=30.0,
            pool=30.0,
        )
        max_attempts = 1 + len(self.retry_backoff_s)
        last_error = ""
        for attempt in range(max_attempts):
            self.breaker.before_call()
            try:
                req = self._http.build_request("POST", path, json=payload, timeout=timeout)
                response = await self._http.send(req, stream=stream)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
                self.breaker.record_failure()
                last_error = f"{type(exc).__name__}: {exc}"
            except httpx.TimeoutException as exc:
                # Model đang chậm, không phải mất kết nối → không tính vào circuit, không retry
                self.breaker.release_trial()
                raise LLMTimeout(f"{profile.name}: quá {profile.timeout_s:.0f} s") from exc
            except httpx.TransportError as exc:
                self.breaker.record_failure()
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code < 400:
                    self.breaker.record_success()
                    return response
                body = (await response.aread()).decode("utf-8", "replace")
                await response.aclose()
                if response.status_code >= 500:
                    self.breaker.record_failure()
                    last_error = f"HTTP {response.status_code}: {body[:300]}"
                else:
                    self.breaker.release_trial()
                    if _CONTEXT_ERR_RE.search(body):
                        raise ContextTooLong(f"LM Studio từ chối vì quá context: {body[:300]}")
                    raise LLMError(
                        f"HTTP {response.status_code}: {body[:300]}", code="LLM_BAD_REQUEST"
                    )
            if attempt < max_attempts - 1:
                await asyncio.sleep(self.retry_backoff_s[attempt])
        raise LLMUnavailable(f"Không gọi được LM Studio sau {max_attempts} lần: {last_error}")

    async def _request_json(
        self, profile: TaskProfile, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self._request(profile, path, payload)
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise LLMError(
                "LM Studio trả dữ liệu không phải JSON", code="LLM_BAD_RESPONSE"
            ) from exc
        return data

    def _text_result(self, data: dict[str, Any], return_thinking: bool) -> TextResult:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("LM Studio không trả choices", code="LLM_BAD_RESPONSE")
        msg = choices[0].get("message") or {}
        visible, inline_think = split_think(msg.get("content") or "")
        thinking = msg.get("reasoning_content") or inline_think or None
        finish = choices[0].get("finish_reason")
        if not visible and finish == "length":
            raise LLMOutputError(
                "Hết max_tokens khi model còn đang suy nghĩ – tăng LLM_REASONING_BUDGET",
                code="REASONING_TRUNCATED",
            )
        return TextResult(
            text=visible,
            thinking=thinking if return_thinking else None,
            finish_reason=finish,
            usage=_usage(data),
        )

    def _log(
        self,
        profile: TaskProfile,
        *,
        error: BaseException | None,
        attempts: int,
        queue_ms: int,
        started: float,
        usage: Usage | None,
        prompt: Any,
        output: str | None,
        caller_ref: str | None,
        model: str | None = None,
    ) -> None:
        err_text: str | None
        if isinstance(error, (asyncio.CancelledError, GeneratorExit)):
            outcome, err_text = "error", "cancelled"
        else:
            outcome = _outcome(error)
            err_text = f"{type(error).__name__}: {error}" if error else None
        keep = self.s.llm_log_content
        try:
            self.call_log.submit(
                CallRecord(
                    task=profile.name,
                    model=model or self.s.llm_model,
                    priority=profile.priority,
                    thinking=bool(profile.thinking),
                    attempts=attempts,
                    outcome=outcome,
                    tokens_in=usage.tokens_in if usage else None,
                    tokens_out=usage.tokens_out if usage else None,
                    reasoning_tokens=usage.reasoning_tokens if usage else None,
                    queue_ms=queue_ms,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    error=err_text,
                    prompt=prompt if keep else None,
                    output=output if keep else None,
                    caller_ref=caller_ref,
                )
            )
        except Exception:
            logger.warning("Không ghi được llm_call_log", exc_info=True)


def _response_format(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        },
    }


def _schema_instruction(schema: type[BaseModel]) -> Message:
    return {
        "role": "system",
        "content": (
            "Chỉ trả về một đối tượng JSON hợp lệ theo JSON Schema sau, không kèm giải thích:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        ),
    }


def _sum_usage(a: Usage, b: Usage) -> Usage:
    def add(x: int | None, y: int | None) -> int | None:
        return None if x is None and y is None else (x or 0) + (y or 0)

    return Usage(
        tokens_in=add(a.tokens_in, b.tokens_in),
        tokens_out=add(a.tokens_out, b.tokens_out),
        reasoning_tokens=add(a.reasoning_tokens, b.reasoning_tokens),
    )
