from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import httpx

from server.common.typing import is_json_object, json_array, json_object
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.types import LLMRequest, ModelDescriptor

if TYPE_CHECKING:
    from server.services.llm.opencode_provider import OpenCodeProvider

###############################################################################
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 16384
_STOP_REASONS = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}

###############################################################################
class _MessagesHTTPError(Exception):
    """Provider HTTP failure that keeps the response body for classification."""

    # -------------------------------------------------------------------------
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"OpenCode Messages API returned {status_code}: {body[:500]}")
        self.status_code = status_code

###############################################################################
class _Payload:
    """Attribute view over a JSON mapping, shaped like an SDK response object."""

    # -------------------------------------------------------------------------
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # -------------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        return _wrap(self._data.get(name))

    # -------------------------------------------------------------------------
    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return json_object(json.loads(json.dumps(self._data)))

###############################################################################
def _wrap(value: Any) -> Any:
    if is_json_object(value):
        return _Payload(value)
    return [_wrap(item) for item in json_array(value)] if isinstance(value, list) else value

###############################################################################
def _image_block(url: str) -> dict[str, Any] | None:
    header, _, data = url.partition(",")
    if not header.startswith("data:") or not data:
        return None
    media_type = header[5:].split(";", 1)[0] or "image/jpeg"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }

###############################################################################
def _content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content.strip() else []
    blocks: list[dict[str, Any]] = []
    for raw_part in json_array(content):
        part = json_object(raw_part)
        if part.get("type") == "text" and str(part.get("text") or "").strip():
            blocks.append({"type": "text", "text": str(part["text"])})
        elif part.get("type") == "image_url":
            url = json_object(part.get("image_url")).get("url")
            block = _image_block(str(url or ""))
            if block is not None:
                blocks.append(block)
    return blocks

###############################################################################
def _tool_input(arguments: Any) -> dict[str, Any]:
    if is_json_object(arguments):
        return arguments
    try:
        loaded: Any = json.loads(arguments or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return json_object(loaded)

###############################################################################
def _messages_and_system(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Map OpenAI chat-shaped messages to Anthropic ``system`` and turns."""

    system_parts: list[str] = []
    turns: list[dict[str, Any]] = []

    def append(role: str, blocks: list[dict[str, Any]]) -> None:
        if not blocks:
            return
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": blocks})

    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content")
        if role in {"system", "developer"}:
            text = "".join(
                str(block.get("text") or "") for block in _content_blocks(content)
            )
            if text.strip():
                system_parts.append(text)
        elif role == "tool":
            append(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": str(message.get("tool_call_id") or ""),
                        "content": str(content or "") or "(no output)",
                    }
                ],
            )
        elif role == "assistant":
            blocks = _content_blocks(content)
            for raw_call in json_array(message.get("tool_calls")):
                call = json_object(raw_call)
                function = json_object(call.get("function"))
                if not function:
                    continue
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(call.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "input": _tool_input(function.get("arguments")),
                    }
                )
            append("assistant", blocks)
        else:
            append("user", _content_blocks(content))
    return "\n\n".join(system_parts), turns

###############################################################################
def _tool_choice(value: Any) -> dict[str, Any] | None:
    if is_json_object(value):
        name = json_object(value.get("function")).get("name")
        return {"type": "tool", "name": name} if name else None
    if value in (None, "auto"):
        return {"type": "auto"}
    if value == "required":
        return {"type": "any"}
    if value == "none":
        return {"type": "none"}
    return {"type": "tool", "name": str(value)}

###############################################################################
def build_messages_payload(**kwargs: Any) -> dict[str, Any]:
    """Translate one Chat Completions call into an Anthropic Messages body."""

    system, turns = _messages_and_system(
        [json_object(item) for item in json_array(kwargs.get("messages"))]
    )
    model = str(kwargs["model"])
    payload: dict[str, Any] = {
        "model": model,
        "messages": turns,
        "max_tokens": int(kwargs.get("max_tokens") or DEFAULT_MAX_TOKENS),
    }
    if system:
        payload["system"] = system
    temperature = kwargs.get("temperature")
    if isinstance(temperature, (int, float)) and not model.lower().startswith(
        "claude"
    ):
        payload["temperature"] = min(max(float(temperature), 0.0), 1.0)
    tools: list[dict[str, Any]] = []
    for raw_tool in json_array(kwargs.get("tools")):
        function = json_object(json_object(raw_tool).get("function"))
        if function:
            tools.append(
                {
                    "name": function.get("name"),
                    "description": function.get("description") or "",
                    "input_schema": function.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
    if tools:
        payload["tools"] = tools
        choice = _tool_choice(kwargs.get("tool_choice"))
        if choice is not None:
            payload["tool_choice"] = choice
    thinking = json_object(json_object(kwargs.get("extra_body")).get("thinking"))
    if thinking.get("type") == "disabled":
        payload["thinking"] = {"type": "disabled"}
    if kwargs.get("stream"):
        payload["stream"] = True
    return payload

###############################################################################
def _usage(raw: Any) -> dict[str, int]:
    usage = json_object(raw)
    prompt = int(usage.get("input_tokens") or 0)
    completion = int(usage.get("output_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }

###############################################################################
def completion_from_message(body: dict[str, Any]) -> _Payload:
    """Shape an Anthropic message like a Chat Completions response."""

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for raw_block in json_array(body.get("content")):
        block = json_object(raw_block)
        if block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input") or {}),
                    },
                }
            )
    message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls
    stop_reason = str(body.get("stop_reason") or "")
    return _Payload(
        {
            "id": body.get("id"),
            "model": body.get("model"),
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": _STOP_REASONS.get(stop_reason, stop_reason or None),
                }
            ],
            "usage": _usage(body.get("usage")),
        }
    )

###############################################################################
def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise _MessagesHTTPError(response.status_code, response.text)

###############################################################################
def _stream_chunks(lines: Iterator[str]) -> Iterator[_Payload]:
    usage: dict[str, Any] = {}
    for line in lines:
        if not line.startswith("data:"):
            continue
        try:
            event = json_object(json.loads(line[5:].strip()))
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "error":
            raise _MessagesHTTPError(500, json.dumps(event.get("error")))
        if kind == "message_start":
            usage.update(json_object(json_object(event.get("message")).get("usage")))
        elif kind == "message_delta":
            usage.update(json_object(event.get("usage")))
        elif kind == "content_block_delta":
            delta = json_object(event.get("delta"))
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield _Payload({"choices": [{"delta": {"content": delta["text"]}}]})
    yield _Payload({"choices": [], "usage": _usage(usage)})

###############################################################################
class _Completions:
    """Chat Completions-shaped facade over OpenCode's Messages endpoint."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        transport: "_OpenCodeMessagesTransport",
        request: LLMRequest | None,
        stage: str,
    ) -> None:
        self._url = f"{transport.base_url}/messages"
        self._headers = {
            **transport._request_headers(request),  # pyright: ignore[reportPrivateUsage]
            "x-api-key": transport.api_key,
            "Authorization": f"Bearer {transport.api_key}",
            "anthropic-version": ANTHROPIC_VERSION,
            "Accept": "application/json",
        }
        self._options: dict[str, Any] = transport.transport_policy.httpx_options(stage)

    # -------------------------------------------------------------------------
    def with_timeout(self, timeout: float) -> None:
        self._options = {**self._options, "timeout": timeout}

    # -------------------------------------------------------------------------
    def create(self, **kwargs: Any) -> Any:
        payload = build_messages_payload(**kwargs)
        if payload.get("stream"):
            return self._stream(payload)
        with httpx.Client(**self._options) as client:
            response = client.post(self._url, headers=self._headers, json=payload)
        _raise_for_status(response)
        return completion_from_message(json_object(response.json()))

    # -------------------------------------------------------------------------
    def _stream(self, payload: dict[str, Any]) -> Iterator[_Payload]:
        with httpx.Client(**self._options) as client:
            with client.stream(
                "POST", self._url, headers=self._headers, json=payload
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    _raise_for_status(response)
                yield from _stream_chunks(response.iter_lines())

    # -------------------------------------------------------------------------
    async def acreate(self, **kwargs: Any) -> Any:
        payload = build_messages_payload(**kwargs)
        async with httpx.AsyncClient(**self._options) as client:
            response = await client.post(self._url, headers=self._headers, json=payload)
        _raise_for_status(response)
        return completion_from_message(json_object(response.json()))

###############################################################################
class _MessagesClient:
    """Drop-in for the SDK client surface DeepSeekProvider consumes."""

    # -------------------------------------------------------------------------
    def __init__(self, completions: _Completions) -> None:
        self.chat = self
        self.completions = completions

    # -------------------------------------------------------------------------
    def with_options(self, *, timeout: float) -> "_MessagesClient":
        self.completions.with_timeout(timeout)
        return self

    # -------------------------------------------------------------------------
    def close(self) -> None:
        return None

###############################################################################
class _AsyncMessagesClient:
    """Async counterpart; ``chat.completions.create`` is awaitable."""

    # -------------------------------------------------------------------------
    def __init__(self, completions: _Completions) -> None:
        self.chat = self
        self.completions = self
        self._completions = completions

    # -------------------------------------------------------------------------
    def with_options(self, *, timeout: float) -> "_AsyncMessagesClient":
        self._completions.with_timeout(timeout)
        return self

    # -------------------------------------------------------------------------
    async def create(self, **kwargs: Any) -> Any:
        return await self._completions.acreate(**kwargs)

    # -------------------------------------------------------------------------
    async def close(self) -> None:
        return None

###############################################################################
class _OpenCodeMessagesTransport(DeepSeekProvider):
    """Anthropic Messages serialization with OpenCode identity and headers.

    Reuses the Chat Completions orchestration (tools, structured function,
    streaming, usage accounting) and swaps only the wire format.
    """

    # -------------------------------------------------------------------------
    def __init__(self, parent: "OpenCodeProvider") -> None:
        super().__init__(
            api_key=parent.api_key,
            base_url=parent.base_url,
            transport_policy=parent.transport_policy,
        )
        self.provider_name = parent.provider_name
        self._parent = parent

    # -------------------------------------------------------------------------
    def _request_headers(self, request: LLMRequest | None = None) -> dict[str, str]:
        return self._parent._request_headers(request)  # pyright: ignore[reportPrivateUsage]

    # -------------------------------------------------------------------------
    def _client(self, request: LLMRequest | None = None, *, stage: str = "chat") -> Any:
        return _MessagesClient(_Completions(self, request, stage))

    # -------------------------------------------------------------------------
    def _async_client(
        self, request: LLMRequest | None = None, *, stage: str = "chat"
    ) -> Any:
        return _AsyncMessagesClient(_Completions(self, request, stage))

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return []

    # -------------------------------------------------------------------------
    def supports_tools(self, model: str) -> bool | None:
        return self._parent.supports_tools(model)

    # -------------------------------------------------------------------------
    def supports_structured_output(self, model: str) -> bool | None:
        return self._parent.supports_structured_output(model)

    # -------------------------------------------------------------------------
    def supports_vision(self, model: str) -> bool | None:
        return self._parent.supports_vision(model)
