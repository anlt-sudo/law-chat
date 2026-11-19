"""Mock LM Studio ở tầng httpx (M01-T2) – không cần mạng, chạy được trong CI.

Mô phỏng đúng định dạng LM Studio đo được ở docs/spikes/lmstudio.md:
- suy nghĩ ở `message.reasoning_content` / `delta.reasoning_content`, `content` sạch;
- `usage.completion_tokens_details.reasoning_tokens`;
- `/api/v0/models` có `state`, `loaded_context_length`.

Kịch bản: đẩy `Script` vào `mock.chat_scripts` theo thứ tự; hết kịch bản → trả `default_chat`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import httpx

LLM = "deepseek-r1-0528-qwen3-8b"
EMB = "text-embedding-nomic-embed-text-v1.5"


@dataclass
class Script:
    content: str = "OK"
    reasoning: str = "Hmm, người dùng hỏi…"
    finish: str = "stop"
    delay_s: float = 0.0
    status: int = 200
    body: str | None = None  # thân lỗi khi status >= 400
    exc: type[Exception] | None = None  # vd httpx.ReadTimeout, httpx.ConnectError
    # stream: danh sách delta tùy chỉnh, vd [{"content": "<thi"}, {"content": "nk>x"}]
    deltas: list[dict[str, str]] | None = None


@dataclass
class MockLMStudio:
    models: tuple[str, ...] = (LLM, EMB)
    loaded: tuple[str, ...] | None = (LLM, EMB)  # None → không có /api/v0/models
    loaded_context_length: int = 16384
    dim: int = 768
    down: bool = False
    chat_scripts: deque[Script] = field(default_factory=deque)
    default_chat: Script = field(default_factory=Script)
    embed_status: int = 200
    requests: list[dict[str, Any]] = field(default_factory=list)
    chat_order: list[str] = field(
        default_factory=list
    )  # nội dung user message cuối, theo thứ tự xử lý

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def script(self, *scripts: Script) -> MockLMStudio:
        self.chat_scripts.extend(scripts)
        return self

    @property
    def chat_requests(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["path"].endswith("/chat/completions")]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("Connection refused", request=request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        self.requests.append({"path": path, "body": body})
        if path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in self.models]})
        if path.endswith("/api/v0/models"):
            if self.loaded is None:
                return httpx.Response(404)
            return httpx.Response(200, json={"data": [self._model_info(m) for m in self.models]})
        if path.endswith("/chat/completions"):
            return await self._chat(request, body)
        if path.endswith("/embeddings"):
            return self._embeddings(body)
        return httpx.Response(404)

    def _model_info(self, m: str) -> dict[str, Any]:
        info: dict[str, Any] = {
            "id": m,
            "type": "embeddings" if m == EMB else "llm",
            "state": "loaded" if self.loaded and m in self.loaded else "not-loaded",
        }
        if info["state"] == "loaded":
            info["loaded_context_length"] = 2048 if m == EMB else self.loaded_context_length
        return info

    async def _chat(self, request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        sc = self.chat_scripts.popleft() if self.chat_scripts else self.default_chat
        if sc.delay_s:
            await asyncio.sleep(sc.delay_s)
        last_user = next(
            (m["content"] for m in reversed(body.get("messages", [])) if m["role"] == "user"), ""
        )
        self.chat_order.append(last_user)
        if sc.exc is not None:
            raise sc.exc("mock", request=request)  # type: ignore[call-arg]
        if sc.status >= 400:
            return httpx.Response(sc.status, text=sc.body or "error")
        usage = {
            "prompt_tokens": 20,
            "completion_tokens": len(sc.reasoning) // 3 + len(sc.content) // 3,
            "completion_tokens_details": {"reasoning_tokens": len(sc.reasoning) // 3},
        }
        if not body.get("stream"):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": sc.finish,
                            "message": {
                                "role": "assistant",
                                "content": sc.content,
                                "reasoning_content": sc.reasoning,
                            },
                        }
                    ],
                    "usage": usage,
                },
            )
        deltas = sc.deltas
        if deltas is None:
            deltas = [{"reasoning_content": sc.reasoning}] if sc.reasoning else []
            deltas += [{"content": sc.content[i : i + 4]} for i in range(0, len(sc.content), 4)]
        lines = [
            _sse({"choices": [{"index": 0, "delta": d, "finish_reason": None}]}) for d in deltas
        ]
        lines.append(_sse({"choices": [{"index": 0, "delta": {}, "finish_reason": sc.finish}]}))
        lines.append(_sse({"choices": [], "usage": usage}))
        lines.append("data: [DONE]\n\n")
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content="".join(lines).encode()
        )

    def _embeddings(self, body: dict[str, Any]) -> httpx.Response:
        if self.embed_status != 200:
            return httpx.Response(self.embed_status, text="error")
        inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
        data = [{"index": i, "embedding": _vec(t, self.dim)} for i, t in enumerate(inputs)]
        return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 5 * len(inputs)}})


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _vec(text: str, dim: int) -> list[float]:
    """Vector xác định theo nội dung (cùng chuỗi → cùng vector)."""
    seed = hashlib.sha256(text.encode()).digest()
    return [((seed[i % len(seed)] / 255.0) - 0.5) for i in range(dim)]
