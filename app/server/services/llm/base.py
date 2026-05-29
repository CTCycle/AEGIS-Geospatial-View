from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any

from server.services.llm.types import (
    LLMRequest,
    LLMResult,
    LLMToolDefinition,
    ModelDescriptor,
)

###############################################################################
class LLMProvider(ABC):
    provider_name: str

    @abstractmethod
    def list_models(self) -> list[ModelDescriptor]: ...

    @abstractmethod
    def chat(
        self,
        request: LLMRequest,
        *,
        tools: Sequence[LLMToolDefinition] | None = None,
        tool_choice: str | None = "auto",
        response_json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    @abstractmethod
    def stream_chat(self, request: LLMRequest) -> Iterable[str]: ...

    @abstractmethod
    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]: ...

    @abstractmethod
    def embeddings(self, *, model: str, input_text: str) -> list[float]: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    def supports_tools(self, model: str) -> bool:
        _ = model
        return False

    def supports_structured_output(self, model: str) -> bool:
        _ = model
        return False

    def normalize_tool_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return messages

    def _validate_request_capabilities(self, request: LLMRequest) -> None:
        if request.tools and request.response_json_schema is not None:
            raise ValueError("LLMRequest cannot combine native tools with structured response_schema")
        if request.tools and not self.supports_tools(request.model):
            raise ValueError(
                f"Model '{request.model}' for provider '{self.provider_name}' does not support native tools."
            )
        if (
            request.response_json_schema is not None
            and not self.supports_structured_output(request.model)
        ):
            raise ValueError(
                f"Model '{request.model}' for provider '{self.provider_name}' does not support structured output."
            )
