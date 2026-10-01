from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import pytest

from server.services.llm.base import LLMProvider
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.errors import LLMStructuredOutputError
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.opencode_provider import OpenCodeProvider
from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolDefinition,
    ModelDescriptor,
)


###############################################################################
class _StubProvider(LLMProvider):
    provider_name = "stub"

    def __init__(self, vision: bool | None) -> None:
        self._vision = vision

    def list_models(self) -> list[ModelDescriptor]:
        return []

    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        return LLMResult(content="")

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        return iter(())

    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        return {}

    async def achat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        return LLMResult(content="")

    async def astructured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        return {}

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        return []

    def health_check(self) -> dict[str, Any]:
        return {"ok": True}

    def supports_vision(self, model: str) -> bool | None:
        return self._vision


###############################################################################
def _request(*, requires_vision: bool) -> LLMRequest:
    return LLMRequest(
        model="model-x",
        messages=[{"role": "user", "content": "hello"}],
        metadata={"requires_vision": True} if requires_vision else {},
    )


###############################################################################
def test_validate_request_capabilities_fails_closed_without_vision() -> None:
    for unsupported in (False, None):
        provider = _StubProvider(vision=unsupported)
        with pytest.raises(LLMStructuredOutputError) as exc_info:
            provider._validate_request_capabilities(  # pyright: ignore[reportPrivateUsage]
                _request(requires_vision=True)
            )
        assert exc_info.value.code == "model_vision_unsupported"


###############################################################################
def test_validate_request_capabilities_allows_vision_when_supported() -> None:
    provider = _StubProvider(vision=True)
    provider._validate_request_capabilities(  # pyright: ignore[reportPrivateUsage]
        _request(requires_vision=True)
    )


###############################################################################
def test_validate_request_capabilities_ignores_requires_vision_when_unset() -> None:
    provider = _StubProvider(vision=False)
    # Without the flag, no image is present and the text request must pass.
    provider._validate_request_capabilities(  # pyright: ignore[reportPrivateUsage]
        _request(requires_vision=False)
    )


###############################################################################
def test_openai_provider_vision_follows_catalog() -> None:
    provider = OpenAIProvider(api_key="test")
    assert provider.supports_vision("gpt-4.1") is True
    assert provider.supports_vision("gpt-4.1-mini") is True
    assert provider.supports_vision("unknown-model") is None


###############################################################################
def test_google_provider_vision_follows_catalog() -> None:
    provider = GoogleProvider(api_key="test")
    assert provider.supports_vision("gemini-2.5-flash") is True
    assert provider.supports_vision("gemini-2.5-pro") is True
    assert provider.supports_vision("unknown-model") is None


###############################################################################
def test_deepseek_provider_is_text_only() -> None:
    provider = DeepSeekProvider(api_key="test", base_url="https://example.invalid")
    assert provider.supports_vision("deepseek-chat") is False
    assert provider.supports_vision("deepseek-v4-flash") is False


###############################################################################
def test_opencode_provider_vision_only_for_explicit_vision_models() -> None:
    provider = OpenCodeProvider(api_key="test", provider_name="opencode")
    assert provider.supports_vision("deepseek-v4-flash-vision-exp") is True
    assert provider.supports_vision("deepseek-v4-flash") is False