from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from pydantic import BaseModel
from tests.conftest import run_async_in_thread

from server.prompts.providers import build_deepseek_json_schema_instruction
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.types import LLMRequest


###############################################################################
class _StructuredPayload(BaseModel):
    answer: str


###############################################################################
class _Completions:
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        message = SimpleNamespace(
            content=json.dumps({"answer": "structured"}),
            tool_calls=[],
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")]
        )


###############################################################################
class _Client:
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.completions = _Completions()
        self.chat = SimpleNamespace(completions=self.completions)


###############################################################################
class _AsyncCompletions:
    # -------------------------------------------------------------------------
    def __init__(self, response: object | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = response or SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps({"answer": "async"}),
                        tool_calls=[],
                    ),
                    finish_reason="stop",
                )
            ]
        )
        self.started = asyncio.Event()
        self.block = False

    # -------------------------------------------------------------------------
    async def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        self.started.set()
        if self.block:
            await asyncio.Future()
        return self.response


###############################################################################
class _AsyncClient:
    # -------------------------------------------------------------------------
    def __init__(self, completions: _AsyncCompletions) -> None:
        self.completions = completions
        self.chat = SimpleNamespace(completions=completions)
        self.options: list[dict[str, object]] = []
        self.closed = False

    # -------------------------------------------------------------------------
    def with_options(self, **kwargs):  # noqa: ANN003, ANN201
        self.options.append(kwargs)
        return self

    # -------------------------------------------------------------------------
    async def close(self) -> None:
        self.closed = True


###############################################################################
def test_structured_output_uses_deepseek_json_object_mode(monkeypatch) -> None:
    client = _Client()
    provider = DeepSeekProvider(api_key="test")
    monkeypatch.setattr(provider, "_client", lambda: client)
    request = LLMRequest(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "Extract the answer."},
            {"role": "user", "content": "Hello"},
        ],
    )

    result = provider.structured_output(request, schema=_StructuredPayload)

    assert result == {"answer": "structured"}
    call = client.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert "JSON schema" in call["messages"][-1]["content"]
    assert '"answer"' in call["messages"][-1]["content"]
    assert sum("JSON schema" in str(message.get("content")) for message in call["messages"]) == 1
    assert call["messages"][-1]["content"] == build_deepseek_json_schema_instruction(
        _StructuredPayload.model_json_schema()
    )


###############################################################################
def test_async_chat_uses_native_transport_and_closes_client(monkeypatch) -> None:
    completions = _AsyncCompletions()
    client = _AsyncClient(completions)
    constructor_calls: list[dict[str, object]] = []

    def build_client(**kwargs):  # noqa: ANN001, ANN202
        constructor_calls.append(kwargs)
        return client

    monkeypatch.setattr("server.services.llm.deepseek_provider.AsyncOpenAI", build_client)
    provider = DeepSeekProvider(api_key="test", base_url="https://provider.test")
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
        metadata={"max_tokens": 7},
    )

    result = run_async_in_thread(provider.achat(request))

    assert result.content == '{"answer": "async"}'
    assert constructor_calls == [
        {
            "api_key": "test",
            "base_url": "https://provider.test",
            "timeout": 30.0,
            "max_retries": 0,
        }
    ]
    assert completions.calls[0]["stream"] is False
    assert completions.calls[0]["max_tokens"] == 7
    assert client.closed is True


###############################################################################
def test_async_structured_output_uses_native_transport(monkeypatch) -> None:
    completions = _AsyncCompletions()
    client = _AsyncClient(completions)
    monkeypatch.setattr(
        "server.services.llm.deepseek_provider.AsyncOpenAI",
        lambda **_kwargs: client,
    )
    provider = DeepSeekProvider(api_key="test")
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Extract"}],
        metadata={"max_output_tokens": 9},
    )

    result = run_async_in_thread(
        provider.astructured_output(request, schema=_StructuredPayload)
    )

    assert result == {"answer": "async"}
    assert completions.calls[0]["stream"] is False
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert completions.calls[0]["max_tokens"] == 9
    assert client.closed is True


###############################################################################
def test_async_chat_cancellation_closes_native_client(monkeypatch) -> None:
    completions = _AsyncCompletions()
    completions.block = True
    client = _AsyncClient(completions)
    monkeypatch.setattr(
        "server.services.llm.deepseek_provider.AsyncOpenAI",
        lambda **_kwargs: client,
    )
    provider = DeepSeekProvider(api_key="test")
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "Hello"}],
    )

    async def cancel_request() -> bool:
        task = asyncio.create_task(provider.achat(request))
        await completions.started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return client.closed

    assert run_async_in_thread(cancel_request()) is True
